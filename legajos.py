import json
import os
import uuid
from datetime import datetime, timezone
from google.cloud import firestore
from google.oauth2 import service_account

CREDS_FILE = "credentials.json"
PROJECT = "admisiones-476215"

TIPOS_PRESENTACION = ["Escrito", "Amparo", "Otros"]
ESTADOS_PRESENTACION = ["Pendiente", "En trámite", "Con resolución", "Resuelto", "Rechazado"]
ESTADOS_NOVEDAD = ["Pendiente", "En trámite", "Con novedades", "Resuelto", "Rechazado"]


def _db():
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json:
        creds_dict = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            CREDS_FILE,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    return firestore.Client(project=PROJECT, credentials=credentials, database="dda-firestore")


def _legajo_ref(db, dni: str):
    return db.collection("legajos").document(dni.replace(".", "").strip())


def _buscar_nombre(dni: str) -> str | None:
    from dda import buscar_por_dni
    resultado = buscar_por_dni(dni)
    return resultado["nombre"] if resultado["encontrado"] else None


def _ensure_legajo(ref, dni: str):
    if not ref.get().exists:
        nombre = _buscar_nombre(dni)
        ref.set({"created_at": datetime.now(timezone.utc), "nombre": nombre})


# ---------- Presentaciones ----------

def add_presentacion(dni: str, fecha: str, tipo: str, descripcion: str,
                     expediente: str = "", estado: str = "Pendiente") -> str:
    db = _db()
    ref = _legajo_ref(db, dni)
    _ensure_legajo(ref, dni)
    doc_id = str(uuid.uuid4())
    ref.collection("presentaciones").document(doc_id).set({
        "fecha": fecha,
        "tipo": tipo,
        "descripcion": descripcion,
        "expediente": expediente,
        "estado": estado,
        "created_at": datetime.now(timezone.utc),
    })
    return doc_id


def update_presentacion(dni: str, doc_id: str, fecha: str, tipo: str,
                        descripcion: str, expediente: str, estado: str):
    db = _db()
    _legajo_ref(db, dni).collection("presentaciones").document(doc_id).update({
        "fecha": fecha,
        "tipo": tipo,
        "descripcion": descripcion,
        "expediente": expediente,
        "estado": estado,
    })


def list_presentaciones(dni: str) -> list[dict]:
    db = _db()
    docs = (
        _legajo_ref(db, dni)
        .collection("presentaciones")
        .order_by("fecha", direction=firestore.Query.DESCENDING)
        .stream()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]


def delete_presentacion(dni: str, doc_id: str):
    db = _db()
    _legajo_ref(db, dni).collection("presentaciones").document(doc_id).delete()


# ---------- Novedades ----------

def add_novedad(dni: str, texto: str, estado: str) -> str:
    db = _db()
    ref = _legajo_ref(db, dni)
    _ensure_legajo(ref, dni)
    doc_id = str(uuid.uuid4())
    ref.collection("novedades").document(doc_id).set({
        "texto": texto,
        "estado": estado,
        "created_at": datetime.now(timezone.utc),
    })
    return doc_id


def list_novedades(dni: str) -> list[dict]:
    db = _db()
    docs = (
        _legajo_ref(db, dni)
        .collection("novedades")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .stream()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]


# ---------- Cobros ----------

def add_cobro(dni: str, concepto: str, monto: float, pagado: float) -> str:
    db = _db()
    ref = _legajo_ref(db, dni)
    _ensure_legajo(ref, dni)
    doc_id = str(uuid.uuid4())
    ref.collection("cobros").document(doc_id).set({
        "concepto": concepto,
        "monto": round(monto, 2),
        "pagado": round(pagado, 2),
        "debe": round(monto - pagado, 2),
        "created_at": datetime.now(timezone.utc),
    })
    return doc_id


def list_cobros(dni: str) -> list[dict]:
    db = _db()
    docs = (
        _legajo_ref(db, dni)
        .collection("cobros")
        .order_by("created_at")
        .stream()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]


def delete_cobro(dni: str, doc_id: str):
    db = _db()
    _legajo_ref(db, dni).collection("cobros").document(doc_id).delete()


def save_resolucion_extra(dni: str, numero: str, tipo: str, plazo: str, partido: str):
    db = _db()
    ref = _legajo_ref(db, dni)
    _ensure_legajo(ref, dni)
    ref.collection("resoluciones").document(numero).set({
        "tipo": tipo,
        "plazo": plazo,
        "partido": partido,
    }, merge=True)


def get_resoluciones_extra(dni: str) -> dict:
    db = _db()
    docs = _legajo_ref(db, dni).collection("resoluciones").stream()
    return {d.id: d.to_dict() for d in docs}


def save_nombre(dni: str, nombre: str):
    db = _db()
    _legajo_ref(db, dni).set({"nombre": nombre}, merge=True)


def list_legajos() -> list[dict]:
    db = _db()
    result = []
    for doc in db.collection("legajos").stream():
        data = doc.to_dict()
        dni = doc.id
        nombre = data.get("nombre")
        if not nombre:
            nombre = _buscar_nombre(dni)
            if nombre:
                _legajo_ref(db, dni).update({"nombre": nombre})
        pres = list(
            db.collection("legajos").document(dni)
            .collection("presentaciones")
            .order_by("fecha", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        pres_data = pres[0].to_dict() if pres else {}
        nov = list(
            db.collection("legajos").document(dni)
            .collection("novedades")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        nov_data = nov[0].to_dict() if nov else {}
        cobros = db.collection("legajos").document(dni).collection("cobros").stream()
        deuda = sum(c.to_dict().get("debe", 0) for c in cobros)
        result.append({
            "dni": dni,
            "nombre": nombre,
            "tipo_presentacion": pres_data.get("tipo"),
            "expediente_presentacion": pres_data.get("expediente"),
            "fecha_presentacion": pres_data.get("fecha"),
            "estado": pres_data.get("estado"),
            "ultima_novedad": nov_data.get("texto"),
            "ultima_novedad_fecha": nov_data.get("created_at"),
            "deuda": round(deuda, 2),
        })
    result.sort(key=lambda x: x["nombre"] or "")
    return result