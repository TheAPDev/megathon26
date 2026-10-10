from greenghar.ocr.bill import parse_text, validate


def test_regex_parse_and_validate():
    text = "TPDDL  Consumer No: 600123456789\nSanctioned Load: 4 kW\nUnits consumed 412\nAmount payable 3,250.00\n" \
           "05/2026 412\n04/2026 398\n03/2026 260\n02/2026 99999"
    v = validate(parse_text(text))
    assert v["consumer_number_masked"].endswith("6789") and v["consumer_number_masked"].startswith("*")
    assert v["sanctioned_load_kw"] == 4
    assert v["monthly_kwh"][4] == 412 and v["monthly_kwh"][2] == 260
    assert v["monthly_kwh"][1] is None and any("implausible" in w for w in v["warnings"])


def test_bimonthly_bills_are_halved():
    v = validate({"history": [{"month": "2026-06", "units": 600}], "billing_period_months": 2})
    assert v["monthly_kwh"][5] == 300


def _pdf(text_lines):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import io
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=A4)
    y = 800
    for ln in text_lines:
        c.drawString(60, y, ln)
        y -= 18
    c.save()
    return b.getvalue()


def test_pdf_bill_text_layer_is_parsed_without_gemini(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from greenghar.ocr.bill import parse_bill
    pdf = _pdf(["TPDDL Electricity Bill", "Consumer No: 600123456789", "Sanctioned Load: 4 kW", "Units consumed 412",
                "Amount payable 3,250.00", "05/2026 412", "04/2026 398", "03/2026 260"])
    v = parse_bill(pdf, "application/pdf")
    assert v["provider"] == "tesseract" and v["monthly_kwh"][4] == 412 and v["sanctioned_load_kw"] == 4


def test_pdf_endpoint_accepts_pdf(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    pdf = _pdf(["Consumer No: 600123456789", "Units consumed 300", "Amount payable 2,100.00", "05/2026 300", "04/2026 280", "03/2026 250"])
    r = client.post("/bills/parse", files={"file": ("bill.pdf", pdf, "application/pdf")})
    assert r.status_code == 200 and r.json()["monthly_kwh"][4] == 300
