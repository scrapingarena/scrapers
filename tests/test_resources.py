from scrapingarena.resources import _parse_bytes


def test_parse_docker_memory_units() -> None:
    assert _parse_bytes("1.5GiB") == round(1.5 * 1024**3)
    assert _parse_bytes("256MiB") == 256 * 1024**2
    assert _parse_bytes("invalid") == 0
