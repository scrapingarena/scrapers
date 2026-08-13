from scrapingarena.scrapers.registry import scraper_names


def test_expected_scrapers_are_registered() -> None:
    assert scraper_names() == [
        "camoufox-fork",
        "camoufox-original",
        "cloakbrowser",
        "curl-cffi",
        "lightpanda",
        "obscura",
        "shardbrowser",
        "steel",
        "wreq",
    ]
