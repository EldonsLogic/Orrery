"""Compile, apply, rollback, export and Blueprint edits through the HTTP API (live, on the real compiler and the fake)."""
from studio_testlib import FIXTURE, load_json


def compile_(client):
    status, body, _ = client.post("/api/compile")
    assert status == (200 if body["ok"] else 409)  # a refusal is a 409 with codes and paths
    return body


def test_state_reports_the_fixture_the_engine_badge_and_no_site(client):
    status, s, _ = client.get("/api/state")
    assert status == 200 and s["ok"]
    fx = load_json(FIXTURE)
    assert s["engine"] == {"kind": "fake", "labelKey": "engine.fake"}
    assert s["blueprint"]["id"] == fx["meta"]["id"]
    assert s["blueprint"]["legalName"] == fx["company"]["legalName"]
    assert s["blueprint"]["counts"]["entities"] == len(fx["entities"])
    assert len(s["components"]) == len(fx["components"]) and all(c["enabled"] for c in s["components"])
    assert s["site"] == {"provisioned": False}


def test_components_carry_eligibility_and_reverse_dependencies(client):
    comps = {c["id"]: c for c in client.get("/api/state")[1]["components"]}
    assert comps["core.customer"]["eligible"] == {"sandbox": True, "production": False}
    assert {"core.sales_invoice", "core.sales_order", "sales.quote"} <= set(comps["core.customer"]["requiredBy"])
    assert comps["core.customer"]["boundEntities"] == ["customer"]
    assert comps["compliance.zatca_sa"]["touchesLedgerOrTax"] is True


def test_default_compile_succeeds_with_85_steps(client):
    body = compile_(client)
    assert body["ok"] is True and body["stepCount"] == 85 == len(body["steps"])
    assert body["artifactId"].startswith("art_")
    assert sum(body["kinds"].values()) == 85
    assert [s["seq"] for s in body["steps"]] == list(range(1, 86))
    assert all({"phase", "kind", "subject", "pointer"} <= set(s) for s in body["steps"])


def test_compile_is_deterministic(client):
    assert compile_(client)["artifactId"] == compile_(client)["artifactId"]


def test_disabling_a_required_component_gives_real_compiler_codes(client):
    status, _, _ = client.put("/api/blueprint/components", {"id": "core.customer", "enabled": False})
    assert status == 200
    body = compile_(client)
    assert body["ok"] is False
    codes = {r["code"] for r in body["refusals"]}
    assert {"BP-CMP-003", "BP-REF-001"} <= codes
    assert all(r["path"].startswith("/") for r in body["refusals"])


def test_refused_compile_applies_nothing(client):
    client.put("/api/blueprint/components", {"id": "core.item", "enabled": False})
    status, body, _ = client.post("/api/apply", {})
    assert status == 409 and body["ok"] is False and body["stage"] == "compile"
    assert "BP-CMP-003" in {r["code"] for r in body["refusals"]}
    assert body["site"] == {"provisioned": False}
    assert client.get("/api/export")[1] == {"ok": True, "provisioned": False}


def test_re_enabling_a_component_restores_the_compile(client):
    client.put("/api/blueprint/components", {"id": "core.customer", "enabled": False})
    client.put("/api/blueprint/components", {"id": "core.customer", "enabled": True})
    body = compile_(client)
    assert body["ok"] and body["stepCount"] == 85


def test_apply_on_the_fake_applies_every_step_and_the_export_hash_matches(client):
    status, body, _ = client.post("/api/apply", {})
    assert status == 200 and body["ok"] is True and body["status"] == "applied"
    assert body["stepStatus"] == {"applied": body["stepCount"]}
    assert body["postConditions"]["passed"] == body["postConditions"]["total"] > 0
    assert body["exportHashMatches"] is True and body["exportHashAfter"] == body["predictedExportHash"]
    assert [s["stage"] for s in body["stages"]] == ["acquire", "inspect", "prepare", "execute", "reconcile", "finalize"]
    assert body["site"]["appliedArtifactId"] == body["artifactId"]
    assert body["compiledArtifactId"] == compile_(client)["artifactId"]


def test_export_after_apply_summarises_the_site(client):
    client.post("/api/apply", {})
    status, e, _ = client.get("/api/export")
    fx = load_json(FIXTURE)
    assert status == 200 and e["provisioned"] is True
    assert e["counts"]["entities"] == len(fx["entities"]) and e["counts"]["roles"] == len(fx["roles"])
    assert {x["id"] for x in e["names"]["entities"]} == {x["id"] for x in fx["entities"]}
    assert e["company"]["legalName"] == fx["company"]["legalName"]
    assert e["retainedCount"] == 0


def test_rollback_of_the_initial_build_is_refused_with_the_contract_code_and_changes_nothing(client):
    client.post("/api/apply", {})
    before = client.get("/api/export")[1]["exportHash"]
    status, body, _ = client.post("/api/rollback")
    assert status == 409 and body["ok"] is False and body["status"] == "rejected"
    assert body["error"]["code"] == "rollback_not_possible" and body["error"]["reasonCode"] == "no_inverse"
    assert body["siteChanged"] is False and client.get("/api/export")[1]["exportHash"] == before


def test_simulated_failure_rolls_the_site_back_to_the_pre_apply_state(client):
    status, body, _ = client.post("/api/apply", {"failAtStep": 40})
    assert status == 409 and body["status"] == "compensated"
    assert body["error"]["code"] == "engine_unavailable" and body["error"]["path"] == "/steps/40"
    assert body["exportHashAfter"] == body["exportHashBefore"]
    assert body["stepStatus"]["compensated"] == 39 and body["stepStatus"]["failed"] == 1
    assert body["site"]["appliedArtifactId"] is None
    e = client.get("/api/export")[1]
    assert e["counts"]["entities"] == 0 and e["retainedCount"] > 0  # site state changed: quarantined leftovers
    ok = client.post("/api/apply", {})[1]
    assert ok["status"] == "applied" and ok["exportHashMatches"]


def test_rollback_with_nothing_applied_is_a_coded_refusal(client):
    status, body, _ = client.post("/api/rollback")
    assert status == 409 and body["error"] == {"code": "STUDIO-ROLLBACK-NOTHING-APPLIED", "path": "/"}


def test_apply_fail_step_is_validated(client):
    for bad in ("3", 0, True, 1.5):
        status, body, _ = client.post("/api/apply", {"failAtStep": bad})
        assert status == 400 and body["error"] == {"code": "STUDIO-FIELD-TYPE", "path": "/failAtStep"}
    status, body, _ = client.post("/api/apply", {"failAtStep": 9999})
    assert status == 400 and body["error"]["code"] == "STUDIO-STEP-OUT-OF-RANGE"


def test_company_names_are_validated_and_flow_into_the_compile(client):
    names = {"legalName": {"ar": "شركة النخبة", "en": "Elite Trading Co."}, "tradeName": {"ar": "النخبة", "en": "Elite"}}
    status, s, _ = client.put("/api/blueprint/company", names)
    assert status == 200 and s["blueprint"]["legalName"] == names["legalName"]
    steps = compile_(client)["steps"]
    assert any(st["property"] == "/legalName" for st in steps)
    for body, path, code in (({"legalName": {"ar": "x"}}, "/legalName/en", "STUDIO-FIELD-MISSING"),
                             ({"legalName": {"ar": " ", "en": "x"}}, "/legalName/ar", "STUDIO-TEXT-EMPTY"),
                             ({"legalName": {"ar": "a" * 201, "en": "x"}}, "/legalName/ar", "STUDIO-TEXT-TOO-LONG"),
                             ({"legalName": {"ar": "a\u0000", "en": "x"}}, "/legalName/ar", "STUDIO-TEXT-CONTROL"),
                             ({"legalName": {"ar": 1, "en": "x"}}, "/legalName/ar", "STUDIO-TEXT-TYPE"),
                             ({"vatNumber": "3"}, "/vatNumber", "STUDIO-FIELD-UNKNOWN")):
        status, b, _ = client.put("/api/blueprint/company", body)
        assert status == 400 and (b["error"]["code"], b["error"]["path"]) == (code, path), body


def test_entity_labels_with_markup_round_trip_as_plain_data(client):
    evil = {"ar": "<script>alert(1)</script>", "en": "<img src=x onerror=alert(1)>"}
    status, s, _ = client.put("/api/blueprint/entities/customer/labels", evil)
    assert status == 200
    entity = next(e for e in s["blueprint"]["entities"] if e["id"] == "customer")
    assert entity["labels"] == evil
    client.post("/api/apply", {})
    exported = next(e for e in client.get("/api/export")[1]["names"]["entities"] if e["id"] == "customer")
    assert exported["labels"] == evil


def test_unknown_entity_and_component_are_404_with_codes(client):
    status, b, _ = client.put("/api/blueprint/entities/nope/labels", {"ar": "a", "en": "b"})
    assert status == 404 and b["error"]["code"] == "STUDIO-ENTITY-UNKNOWN"
    status, b, _ = client.put("/api/blueprint/components", {"id": "nope", "enabled": False})
    assert status == 404 and b["error"] == {"code": "STUDIO-COMPONENT-UNKNOWN", "path": "/id"}
    status, b, _ = client.put("/api/blueprint/components", {"id": "core.item", "enabled": "no"})
    assert status == 400 and b["error"] == {"code": "STUDIO-FIELD-TYPE", "path": "/enabled"}


def test_reset_restores_the_fixture_and_a_fresh_site(client):
    client.put("/api/blueprint/company", {"tradeName": {"ar": "س", "en": "S"}})
    client.put("/api/blueprint/components", {"id": "core.customer", "enabled": False})
    client.post("/api/apply", {})
    client.put("/api/blueprint/components", {"id": "core.customer", "enabled": True})
    client.post("/api/apply", {})
    status, s, _ = client.post("/api/reset")
    fx = load_json(FIXTURE)
    assert status == 200 and s["blueprint"]["tradeName"] == fx["company"]["tradeName"]
    assert s["site"] == {"provisioned": False} and all(c["enabled"] for c in s["components"])
    assert compile_(client)["stepCount"] == 85
