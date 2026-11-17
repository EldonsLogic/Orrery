"""Brand tokens through the real resolver, and the invoice view against the dataset's stored figures."""
import pytest

from studio_testlib import DATA, load_json

from components.compliance.zatca_sa.phase1 import decode_phase1_tlv

MARKET_FILES = {"ksa": "ksa.json", "uae": "uae.json", "egy": "egy.json", "qat": "qat.json"}


def theme(client, colour):
    status, _, _ = client.put("/api/blueprint/branding", {"primaryColour": colour})
    assert status == 200
    status, body, _ = client.post("/api/theme")
    assert status == (200 if body["ok"] else 409)  # a refused colour is a 409 carrying the findings
    return body


def test_fixture_colour_is_accepted_with_adjustments_in_both_themes(client):
    body = client.post("/api/theme")[1]
    assert body["ok"] is True and body["input"] == "#0F8A7E"
    assert "TKN-ADJ-LIGHT-PRIMARY-DARKENED" in body["codes"]["adjustment"]
    assert body["resolved"]["light"]["--color-primary"] != body["platform"]["light"]["--color-primary"]
    assert set(body["resolved"]) == {"light", "dark"}


@pytest.mark.parametrize("colour,code", [("#C8102E", "TKN-COLOUR-NEAR-CRIMSON"), ("#808080", "TKN-COLOUR-GREY")])
def test_refused_colour_keeps_the_platform_colour(client, colour, code):
    body = theme(client, colour)
    assert body["ok"] is False and code in body["codes"]["refusal"]
    assert body["platformKept"] is True
    for mode in ("light", "dark"):
        assert body["resolved"][mode]["--color-primary"] == body["platform"][mode]["--color-primary"]


def test_theme_returns_only_the_allow_listed_tokens(client):
    body = client.post("/api/theme")[1]
    for mode in ("light", "dark"):
        assert set(body["resolved"][mode]) <= {
            "--color-primary", "--color-primary-hover", "--color-primary-pressed", "--color-primary-label",
            "--color-link-visited", "--state-selected", "--state-secondary-hover", "--color-accent", "--color-background",
            "--color-surface", "--color-surface-raised", "--color-text", "--color-text-muted", "--color-border",
            "--color-success", "--color-warning", "--color-danger"}


@pytest.mark.parametrize("bad", ["zz", "#12345", "#GGGGGG", "0F8A7E", 123, None])
def test_invalid_hex_is_a_400_with_a_code(client, bad):
    status, body, _ = client.put("/api/blueprint/branding", {"primaryColour": bad})
    assert status == 400 and body["error"] == {"code": "STUDIO-HEX-INVALID", "path": "/primaryColour"}
    assert client.get("/api/state")[1]["blueprint"]["primaryColour"] == "#0F8A7E"


@pytest.mark.parametrize("market", sorted(MARKET_FILES))
def test_invoice_figures_are_the_dataset_values_verbatim(client, market):
    data = load_json(DATA / MARKET_FILES[market])
    for inv in data["sales_invoices"]:
        status, body, _ = client.get(f"/api/invoice?market={market}&lang=en&invoice={inv['id']}")
        assert status == 200 and body["synthetic"] is True
        assert body["expected"] == inv["expected"]
        assert [ln["lineNet"] for ln in body["lines"]] == [ln["line_net"] for ln in inv["lines"]]
        assert [ln["unitPrice"] for ln in body["lines"]] == [ln["unit_price"] for ln in inv["lines"]]
        assert body["vatRatePercent"] == data["config"]["vat"]["rate_percent"]
        tags = decode_phase1_tlv(body["qr"]["payload"])
        assert tags[4] == inv["expected"]["total"] and tags[5] == inv["expected"]["vat_amount"]
        assert tags[2] == data["tenant"]["vat_number"] and tags[1] == data["tenant"]["legal_name_ar"]
        assert body["qr"]["tags"] == {str(k): v for k, v in tags.items()}


def test_invoice_arabic_is_rtl_with_bilingual_names_and_western_digits(client):
    body = client.get("/api/invoice?market=ksa&lang=ar")[1]
    assert body["dir"] == "rtl" and body["lang"] == "ar"
    assert body["lines"][0]["name"]["ar"] and body["lines"][0]["name"]["en"]
    assert body["seller"]["legalName"]["ar"] and body["buyer"]["name"]["en"]
    assert all(ch in "0123456789." for ch in body["expected"]["total"])
    assert body["label"] == "synthetic test expectations, not tax authority output"


@pytest.mark.parametrize("query,code,path", [("market=xx", "STUDIO-QUERY-MARKET", "/market"),
                                             ("lang=fr", "STUDIO-QUERY-LANG", "/lang"),
                                             ("market=ksa&market=uae", "STUDIO-QUERY-REPEATED", "/market"),
                                             ("foo=1", "STUDIO-QUERY-UNKNOWN", "/foo"),
                                             ("invoice=INV-9999", "STUDIO-INVOICE-UNKNOWN", "/invoice")])
def test_invoice_query_is_validated(client, query, code, path):
    status, body, _ = client.get("/api/invoice?" + query)
    assert status in (400, 404) and body["error"]["code"] == code and body["error"]["path"] == path
