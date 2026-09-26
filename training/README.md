# Fine-tuning Laya (portable)

Head-only fine-tune of Laya on our 15-action vocabulary. Runs on **Apple Silicon
(MPS)**, **NVIDIA (CUDA)**, or CPU. No machine-specific paths — the `laya` package
auto-downloads the base checkpoint.

> Do NOT run this on the Arch laptop `t-rex-as` — it throws uncorrected CPU
> Machine Check Exceptions under sustained load and hard-crashes. Use the Mac or
> the GTX 1650 box.

## 1. Get the project onto the training machine

Either transport works — the whole project is small:
- **git:** push from the main machine, clone here, or
- **copy:** `scp`/USB/cloud the whole `Controtal/` folder.

## 2. Install PyTorch for the target (do this FIRST)

**Apple Silicon Mac (recommended):**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install torch                     # ships the MPS (Metal) build
```

**NVIDIA GTX 1650 (Linux):**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## 3. Install the rest + this project

```bash
pip install -e .                      # makes `controller` importable
pip install -r training/requirements.txt
```

## 4. Run

```bash
python training/finetune.py           # auto-detects cuda > mps > cpu
# or force: --device mps  |  --device cuda
```
On Apple Silicon, if any op isn't implemented on Metal:
```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 python training/finetune.py --device mps
```

You'll see: `BEFORE` baseline accuracy, per-epoch progress, then `AFTER` accuracy
+ fitted temperature. The dataset lives in `training/data/` (regenerate with
`python training/generate_dataset.py`).

## 5. Bring the result back

The fine-tuned checkpoint is written to `training/laya-finetuned/`
(`model.safetensors` + `encoder/` + `tokenizer/` + `rl_agent_config.json`).
Copy that whole folder back to the main machine — the app will load it from there
(loader wiring is the next step once we have a trained checkpoint).
