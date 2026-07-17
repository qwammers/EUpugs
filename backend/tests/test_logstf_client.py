from app.clients.logstf_client import LogsTfClient


def test_parse_log_ids_accepts_canonical_and_common_typo_domains() -> None:
    text = "Results: https://logs.tf/4087966 and https://loogs.tf/4087967"

    assert LogsTfClient().parse_log_ids(text) == {4087966, 4087967}


def test_parse_log_id_accepts_case_and_json_urls() -> None:
    assert LogsTfClient().parse_log_id("HTTPS://WWW.LOOGS.TF/json/4087968") == 4087968
