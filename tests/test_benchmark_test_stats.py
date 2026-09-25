from pathlib import Path
from runpy import run_path

import pytest

parse_summary = run_path(
    str(Path(__file__).parents[1] / "scripts/benchmark_test_stats.py")
)["parse_summary"]


def test_parses_timestamped_summary() -> None:
    log = (
        "2026-09-27T12:00:00Z curl-cffi-nodemaven: 4/5 success (80.00%), "
        "median-total=15.0ms, proxy-connect-failures=1"
    )
    assert parse_summary(log, "curl-cffi-nodemaven") == ["4/5", "80.00%", "15.0", "1"]


def test_missing_summary_is_not_zero_success() -> None:
    assert parse_summary("installation failed", "wreq-nodemaven") == ["—"] * 4


def test_last_matching_summary_wins() -> None:
    log = (
        "wreq-nodemaven: 1/5 success (20.00%), "
        "median-total=12ms, proxy-connect-failures=0\n"
        "wreq-nodemaven: 0/5 success (0.00%), "
        "median-total=Nonems, proxy-connect-failures=5"
    )
    assert parse_summary(log, "wreq-nodemaven") == ["0/5", "0.00%", "—", "5"]
    assert parse_summary(log, "steel-nodemaven") == ["—"] * 4


def test_table_contains_only_requested_columns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    script = run_path(
        str(Path(__file__).parents[1] / "scripts/benchmark_test_stats.py")
    )
    main = script["main"]
    monkeypatch.setattr(
        "sys.argv", ["stats", "https://github.com/org/repo/actions/runs/1"]
    )
    monkeypatch.setitem(main.__globals__, "token", lambda: None)

    def fetch(path: str, credential: str | None) -> str:
        if path.endswith("/logs"):
            return (
                "fortress-nodemaven: 50/100 success (50.00%), "
                "median-total=6760.69ms, proxy-connect-failures=1"
            )
        return json.dumps(
            {
                "jobs": [
                    {
                        "name": "test-fortress-nodemaven-unfiltered",
                        "id": 1,
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        )

    monkeypatch.setitem(main.__globals__, "fetch", fetch)
    main()
    output = capsys.readouterr().out
    assert "| Scraper | Proxy type | Success rate |" in output
    assert "| fortress | nodemaven-unfiltered | 50.00% |" in output
    assert "Median" not in output


def test_denied_logs_fail_without_empty_table(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    from email.message import Message
    from io import BytesIO
    from urllib.error import HTTPError

    script = run_path(
        str(Path(__file__).parents[1] / "scripts/benchmark_test_stats.py")
    )
    main = script["main"]
    monkeypatch.setattr(
        "sys.argv", ["stats", "https://github.com/org/repo/actions/runs/1"]
    )
    monkeypatch.setitem(main.__globals__, "token", lambda: None)

    def fetch(path: str, credential: str | None) -> str:
        if path.endswith("/logs"):
            raise HTTPError(
                path,
                403,
                "Forbidden",
                Message(),
                BytesIO(b'{"message": "Must have admin rights to Repository."}'),
            )
        return json.dumps(
            {
                "jobs": [
                    {
                        "name": "test-wreq-nodemaven-filtered",
                        "id": 1,
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        )

    monkeypatch.setitem(main.__globals__, "fetch", fetch)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert "Must have admin rights to Repository." in output.err
    assert "gh auth login" in output.err
    assert output.out == ""


def test_github_token_is_not_forwarded_to_log_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.request
    from http.client import HTTPMessage
    from io import BytesIO
    from unittest.mock import MagicMock

    script = run_path(
        str(Path(__file__).parents[1] / "scripts/benchmark_test_stats.py")
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b"log data"
    urlopen = MagicMock(return_value=response)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert (
        script["fetch"]("/repos/org/repo/actions/jobs/1/logs", "test-token")
        == "log data"
    )
    request = urlopen.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer test-token"
    redirected = urllib.request.HTTPRedirectHandler().redirect_request(
        request,
        BytesIO(),
        302,
        "Found",
        HTTPMessage(),
        "https://logs.example.com/signed-log",
    )
    assert redirected is not None
    assert redirected.get_header("Authorization") is None
