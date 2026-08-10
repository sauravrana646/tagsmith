from tagsmith.cli import _prompt_existing_label


def test_prompt_existing_label_by_index(monkeypatch) -> None:
    prompts: list[str] = []

    def fake_prompt(text: str, default: str | None = None) -> str:
        _ = text
        prompts.append(str(default))
        return "3"

    monkeypatch.setattr("tagsmith.cli.typer.prompt", fake_prompt)
    active = ["bill-due", "newsletter", "promotion", "refund"]
    assert _prompt_existing_label(active, default="promotion") == "promotion"
    assert prompts == ["3"]


def test_prompt_existing_label_by_key(monkeypatch) -> None:
    def fake_prompt(text: str, default: str | None = None) -> str:
        _ = text, default
        return "refund"

    monkeypatch.setattr("tagsmith.cli.typer.prompt", fake_prompt)
    active = ["bill-due", "newsletter", "promotion", "refund"]
    assert _prompt_existing_label(active) == "refund"


def test_prompt_existing_label_rejects_bad_then_accepts(monkeypatch) -> None:
    answers = iter(["99", "2"])

    def fake_prompt(text: str, default: str | None = None) -> str:
        _ = text, default
        return next(answers)

    monkeypatch.setattr("tagsmith.cli.typer.prompt", fake_prompt)
    active = ["bill-due", "newsletter", "promotion"]
    assert _prompt_existing_label(active) == "newsletter"
