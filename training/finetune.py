"""Head-only fine-tune of Laya on our action vocabulary. Portable: CUDA / MPS / CPU.

Why head-only: the encoder is 395M params, the decision head 26.5M. We freeze
the encoder, cache its outputs once, and train just the head — fast on any GPU,
tolerable on CPU. We train WITH the 'none' option and unrelated examples so Laya
also learns to abstain (fixing the zero-shot 'none' over-picking).

Depends only on the `laya` pip package (which auto-downloads the checkpoint) plus
this project's action registry — no machine-specific paths, so it runs anywhere:

    python training/finetune.py                 # auto device: cuda > mps > cpu
    python training/finetune.py --device mps     # Apple Silicon
    python training/finetune.py --device cuda    # NVIDIA
    python training/finetune.py --epochs 40 --lr 1e-4
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

import torch
import torch.nn.functional as F

from controller.actions.registry import REGISTRY
from controller.decision.laya import QUESTION_ID, build_action_question

MODEL_ID = "convaiinnovations/laya"
DATA = Path(__file__).resolve().parent / "data"
OUT = Path(__file__).resolve().parent / "laya-finetuned"


def pick_device(pref: str | None) -> str:
    if pref:
        return pref
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text().splitlines() if line]


def build_options() -> list[str]:
    """Option keys in the exact order inference uses (registry order, then none)."""
    q = build_action_question(list(REGISTRY.keys()), allow_none=True)
    return list(q[QUESTION_ID]["criteria"].keys())


def encode_all(agent, rows, question, device):
    """Run the frozen encoder once per example; cache last_hidden_state + markers."""
    import time

    from laya.common import QTYPES, build_sequence

    q_internal = agent._to_internal(question[QUESTION_ID])
    cache = []
    agent.model.encoder.eval()
    t0 = time.time()
    with torch.no_grad():
        for i, r in enumerate(rows):
            ids, markers = build_sequence(
                agent.tok, r["text"], q_internal,
                agent.cfg["max_len"], agent.cfg["head_max_len"],
            )
            input_ids = torch.tensor([ids], device=device)
            attn = torch.ones_like(input_ids)
            h = agent.model.encoder(
                input_ids=input_ids, attention_mask=attn
            ).last_hidden_state[0].cpu()  # [L, D]
            if (i + 1) % 20 == 0 or i + 1 == len(rows):
                el = time.time() - t0
                print(f"  encoded {i+1}/{len(rows)}  ({el:.0f}s, {el/(i+1):.2f}s/ex)", flush=True)
            cache.append({
                "h": h,
                "markers": torch.tensor(markers),
                "label": r["label"],
                "qtype": QTYPES["choice"],
            })
    return cache


def head_logits(model, batch, device):
    """Reproduce DecisionModel's head-forward on cached encoder outputs."""
    hs = [b["h"] for b in batch]
    L = max(h.size(0) for h in hs)
    D = hs[0].size(1)
    n = len(batch)
    K = max(b["markers"].numel() for b in batch)

    h = torch.zeros(n, L, D)
    attn = torch.zeros(n, L, dtype=torch.bool)
    mpos = torch.zeros(n, K, dtype=torch.long)
    mmask = torch.zeros(n, K, dtype=torch.bool)
    for i, b in enumerate(batch):
        li = b["h"].size(0)
        h[i, :li] = b["h"]
        attn[i, :li] = True
        k = b["markers"].numel()
        mpos[i, :k] = b["markers"]
        mmask[i, :k] = True
    h, attn, mpos, mmask = h.to(device), attn.to(device), mpos.to(device), mmask.to(device)

    qtype = torch.zeros(n, dtype=torch.long, device=device)  # choice
    h = h + model.type_emb(qtype)[:, None, :]
    pad = ~attn
    for layer in model.head.layers:
        h = layer(h, src_key_padding_mask=pad)
    idx = mpos.clamp(min=0)[:, :, None].expand(-1, -1, h.size(-1))
    m = torch.gather(h, 1, idx)
    logits = model.scorer(m).squeeze(-1).float()
    return logits.masked_fill(~mmask, -1e4)


def fit_temperature(logits: torch.Tensor, labels: torch.Tensor) -> float:
    """1-D temperature scaling: minimize NLL on held-out logits (CPU, tiny)."""
    logits, labels = logits.cpu(), labels.cpu()
    logT = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([logT], lr=0.1, max_iter=50)

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits / logT.exp(), labels)
        loss.backward()
        return loss

    opt.step(closure)
    return float(logT.exp().item())


def evaluate(model, cache, device, temperature=1.0):
    model.eval()
    correct, confs = 0, []
    with torch.no_grad():
        for i in range(0, len(cache), 32):
            batch = cache[i:i + 32]
            logits = head_logits(model, batch, device) / temperature
            p = torch.softmax(logits, -1)
            for j, b in enumerate(batch):
                pred = int(p[j].argmax())
                correct += pred == b["label"]
                confs.append(float(p[j, b["label"]]))
    return correct / len(cache), sum(confs) / len(confs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=None, help="cuda | mps | cpu (default: auto)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    device = torch.device(pick_device(args.device))
    print(f"device: {device}")

    from laya import RLAgent

    agent = RLAgent(MODEL_ID, device=str(device))
    model = agent.model
    options = build_options()
    idx_of = {a: i for i, a in enumerate(options)}
    question = build_action_question(list(REGISTRY.keys()), allow_none=True)

    train_rows = load_rows("train.jsonl")
    eval_rows = load_rows("eval.jsonl")
    for r in train_rows + eval_rows:
        r["label"] = idx_of[r["action"]]

    print(f"encoding {len(train_rows)} train + {len(eval_rows)} eval (frozen encoder)...")
    train_cache = encode_all(agent, train_rows, question, device)
    eval_cache = encode_all(agent, eval_rows, question, device)

    # Freeze encoder; train head only (skip act_head — it's for escalate, unused here).
    model.encoder.requires_grad_(False)
    head_params = [p for n, p in model.named_parameters()
                   if not n.startswith("encoder") and not n.startswith("act_head")]
    for p in head_params:
        p.requires_grad_(True)
    opt = torch.optim.AdamW(head_params, lr=args.lr, weight_decay=0.01)

    # Inverse-frequency class weights to counter open_app/switch_workspace dominance.
    freq = Counter(r["label"] for r in train_rows)
    weights = torch.tensor(
        [1.0 / freq.get(i, 1) for i in range(len(options))], device=device
    )
    weights = weights / weights.mean()

    base_acc, base_conf = evaluate(model, eval_cache, device)
    print(f"BEFORE  eval acc={base_acc:.3f}  mean-conf(correct)={base_conf:.3f}")

    import random
    for epoch in range(args.epochs):
        model.train()
        random.shuffle(train_cache)
        total = 0.0
        for i in range(0, len(train_cache), args.batch):
            batch = train_cache[i:i + args.batch]
            logits = head_logits(model, batch, device)
            labels = torch.tensor([b["label"] for b in batch], device=device)
            loss = F.cross_entropy(logits, labels, weight=weights)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss) * len(batch)
        if (epoch + 1) % 5 == 0 or epoch == 0:
            acc, conf = evaluate(model, eval_cache, device)
            print(f"epoch {epoch+1:3d}  loss={total/len(train_cache):.4f}  "
                  f"eval acc={acc:.3f}  conf={conf:.3f}", flush=True)

    # Fit temperature on eval logits.
    model.eval()
    with torch.no_grad():
        all_logits, all_labels = [], []
        for i in range(0, len(eval_cache), 32):
            batch = eval_cache[i:i + 32]
            all_logits.append(head_logits(model, batch, device).cpu())
            all_labels += [b["label"] for b in batch]
        logits_cat = torch.cat(all_logits)
        labels_cat = torch.tensor(all_labels)
    T = fit_temperature(logits_cat, labels_cat)
    acc, conf = evaluate(model, eval_cache, device, temperature=T)
    print(f"AFTER   eval acc={acc:.3f}  conf={conf:.3f}  (T={T:.3f})")

    save_checkpoint(model, agent.cfg, len(options), T)
    print(f"saved fine-tuned checkpoint -> {OUT}")


def save_checkpoint(model, cfg, n_options, temperature):
    from huggingface_hub import snapshot_download
    from laya.common import temp_bucket
    from safetensors.torch import save_file

    # Source checkpoint dir (already cached from load) for encoder/tokenizer configs.
    src = Path(snapshot_download(MODEL_ID))
    OUT.mkdir(parents=True, exist_ok=True)
    for sub in ("encoder", "tokenizer"):
        dst = OUT / sub
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src / sub, dst)

    # Update the temperature bucket for our option count (choice:11+ for 16 options).
    cfg = dict(cfg)
    bucket = temp_bucket(0, n_options)
    tbo = dict(cfg.get("temperature_by_options", {}))
    tbo[bucket] = temperature
    cfg["temperature_by_options"] = tbo
    (OUT / "rl_agent_config.json").write_text(json.dumps(cfg, indent=2))

    state = {k: v.contiguous().cpu() for k, v in model.state_dict().items()}
    save_file(state, str(OUT / "model.safetensors"))


if __name__ == "__main__":
    main()
