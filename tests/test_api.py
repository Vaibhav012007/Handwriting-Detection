from fastapi.testclient import TestClient
from io import BytesIO
from PIL import Image
import medkg.api as api
from medkg.api import app

client=TestClient(app)

def test_health_and_search():
    health=client.get("/health"); assert health.status_code == 200
    assert health.json()["catalog"]["medicine_nodes"] >= 2
    response=client.get("/medicines/search", params={"q":"Aceta"})
    assert response.status_code == 200 and response.json()["candidates"]

def test_evidence_and_validation():
    assert client.get("/medicines/SYN-ACETA-500-TAB/evidence").status_code == 200
    assert client.get("/medicines/search", params={"q":" "}).status_code == 422

def test_recognition_response_contains_real_resolver_candidate(monkeypatch):
    monkeypatch.setattr(api, "run_ocr", lambda image: ("Aceta", .91))
    image=BytesIO(); Image.new("RGB", (4,4), "white").save(image, format="PNG")
    response=client.post("/prescriptions", files={"image":("word.png",image.getvalue(),"image/png")})
    recognition=response.json()["recognition"]
    assert response.status_code == 201
    assert recognition["original_text"] == "Aceta"
    assert recognition["candidates"][0]["medicine_id"] == "SYN-ACETA-500-TAB"

def test_dashboard_is_served_with_candidate_and_evidence_ui():
    body=client.get("/").text
    assert "Candidates" in body and "Show graph evidence" in body
