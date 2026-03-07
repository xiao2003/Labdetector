from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def run_llm_finetune(
    *,
    train_path: str,
    eval_path: str = "",
    output_dir: str,
    base_model: str,
    epochs: int = 1,
    batch_size: int = 1,
    learning_rate: float = 2e-4,
    lora_r: int = 8,
    lora_alpha: int = 16,
) -> Dict[str, Any]:
    try:
        import torch
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
        from peft import LoraConfig, TaskType, get_peft_model
    except Exception as exc:
        raise RuntimeError(f"??????????: {exc}") from exc

    train_file = Path(train_path)
    eval_file = Path(eval_path) if eval_path else None
    if not train_file.exists():
        raise FileNotFoundError(f"??????: {train_file}")

    def load_jsonl(path: Path) -> list[dict[str, Any]]:
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    train_rows = load_jsonl(train_file)
    eval_rows = load_jsonl(eval_file) if eval_file and eval_file.exists() else []
    if not train_rows:
        raise RuntimeError("????????????")

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(base_model, trust_remote_code=True)

    peft_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=max(1, int(lora_r)),
        lora_alpha=max(1, int(lora_alpha)),
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, peft_config)

    def render_example(row: Dict[str, Any]) -> Dict[str, Any]:
        text = f"### ??\n{row.get('instruction', '')}\n\n### ??\n{row.get('output', '')}"
        tokenized = tokenizer(text, truncation=True, max_length=1024)
        tokenized["labels"] = list(tokenized["input_ids"])
        return tokenized

    train_dataset = Dataset.from_list(train_rows).map(render_example, remove_columns=list(train_rows[0].keys()))
    eval_dataset = None
    if eval_rows:
        eval_dataset = Dataset.from_list(eval_rows).map(render_example, remove_columns=list(eval_rows[0].keys()))

    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=max(1, int(epochs)),
        per_device_train_batch_size=max(1, int(batch_size)),
        per_device_eval_batch_size=max(1, int(batch_size)),
        learning_rate=float(learning_rate),
        logging_steps=5,
        save_strategy="epoch",
        evaluation_strategy="epoch" if eval_dataset is not None else "no",
        fp16=bool(torch.cuda.is_available()),
        remove_unused_columns=False,
        report_to=[],
    )

    trainer = Trainer(model=model, args=args, train_dataset=train_dataset, eval_dataset=eval_dataset)
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    return {
        "output_dir": str(output_dir),
        "train_samples": len(train_rows),
        "eval_samples": len(eval_rows),
        "base_model": base_model,
    }
