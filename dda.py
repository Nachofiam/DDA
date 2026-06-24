"""
Sistema DDA - Gestión de consultas de clientes
Busca personas por DNI en las resoluciones y registra consultas entrantes.
"""

import uuid
from datetime import datetime, timezone
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT = "admisiones-476215"
DATASET = "Admisiones"
CREDS_FILE = "credentials.json"


def _client():
    credentials = service_account.Credentials.from_service_account_file(CREDS_FILE)
    return bigquery.Client(project=PROJECT, credentials=credentials)


def buscar_por_dni(dni: str) -> dict:
    """
    Busca una persona por DNI y devuelve su nombre y todas las resoluciones
    donde aparece mencionada.

    Returns:
        {
            "encontrado": bool,
            "dni": str,
            "nombre": str | None,
            "resoluciones": [
                {
                    "numero": str,
                    "fecha": date,
                    "pdf": str,
                    "drive_id": str,
                }
            ]
        }
    """
    # Limpiar DNI (aceptar con o sin puntos)
    dni_limpio = dni.replace(".", "").strip()

    client = _client()

    query = """
        SELECT
            p.nombre_completo,
            p.numero_reso,
            d.fecha_reso,
            d.nombre_pdf,
            d.drive_file_id
        FROM `admisiones-476215.Admisiones.sanciones_personas` p
        LEFT JOIN `admisiones-476215.Admisiones.sanciones_documentos` d
            ON p.doc_id = d.doc_id
        WHERE p.dni = @dni
        ORDER BY d.fecha_reso DESC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("dni", "STRING", dni_limpio)]
    )

    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        # Intentar también en tabla Sanciones (tiene campo dni directo)
        query2 = """
            SELECT nombre_normalizado, resolucion_numero, resolucion_fecha
            FROM `admisiones-476215.Admisiones.Sanciones`
            WHERE dni = @dni
            ORDER BY resolucion_fecha DESC
        """
        rows2 = list(client.query(query2, job_config=job_config).result())
        if not rows2:
            return {"encontrado": False, "dni": dni_limpio, "nombre": None, "resoluciones": []}

        nombre = rows2[0]["nombre_normalizado"]
        resoluciones = [
            {
                "numero": r["resolucion_numero"],
                "fecha": r["resolucion_fecha"],
                "pdf": None,
                "drive_id": None,
                "tipo": None,
                "plazo": None,
                "partido": None,
            }
            for r in rows2
        ]
        return {"encontrado": True, "dni": dni_limpio, "nombre": nombre, "resoluciones": resoluciones}

    nombre = rows[0]["nombre_completo"]
    resoluciones = [
        {
            "numero": r["numero_reso"],
            "fecha": r["fecha_reso"],
            "pdf": r["nombre_pdf"],
            "drive_id": r["drive_file_id"],
            "tipo": None,
            "plazo": None,
            "partido": None,
        }
        for r in rows
    ]
    return {"encontrado": True, "dni": dni_limpio, "nombre": nombre, "resoluciones": resoluciones}


def registrar_consulta(
    dni: str,
    canal: str = "whatsapp",
    motivo: str = "",
    notas: str = "",
    resuelto: bool = False,
) -> str:
    """
    Registra una consulta entrante en la tabla dda_consultas.
    Busca el nombre automáticamente a partir del DNI.

    Args:
        dni: DNI del consultante
        canal: 'whatsapp' | 'email' | 'presencial' | 'telefono'
        motivo: texto libre describiendo el motivo de la consulta
        notas: notas internas adicionales
        resuelto: si la consulta ya fue resuelta

    Returns:
        ID de la consulta generada
    """
    resultado = buscar_por_dni(dni)
    nombre = resultado["nombre"] if resultado["encontrado"] else None
    consulta_id = str(uuid.uuid4())

    client = _client()
    table_ref = f"{PROJECT}.{DATASET}.dda_consultas"

    rows = [
        {
            "id": consulta_id,
            "dni": dni.replace(".", "").strip(),
            "nombre": nombre,
            "canal": canal,
            "motivo": motivo,
            "notas": notas,
            "fecha_consulta": datetime.now(timezone.utc).isoformat(),
            "resuelto": resuelto,
        }
    ]

    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"Error al insertar consulta: {errors}")

    return consulta_id


TIPOS_INTERVENCION = ["Presentación", "Conversación con cliente", "Nota interna"]

ESTADOS_INTERVENCION = ["Pendiente", "En proceso", "Resuelto", "Rechazado"]


def crear_tabla_intervenciones():
    client = _client()
    schema = [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("dni", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("nombre", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("fecha", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("tipo_intervencion", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("expediente", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("observaciones", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("estado", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table_ref = f"{PROJECT}.{DATASET}.dda_intervenciones"
    table = bigquery.Table(table_ref, schema=schema)
    try:
        client.create_table(table)
    except Exception:
        pass  # ya existe


def registrar_intervencion(
    dni: str,
    nombre: str,
    fecha: str,
    tipo_intervencion: str,
    expediente: str,
    observaciones: str,
    estado: str,
) -> str:
    intervencion_id = str(uuid.uuid4())
    client = _client()
    rows = [{
        "id": intervencion_id,
        "dni": dni.replace(".", "").strip(),
        "nombre": nombre or None,
        "fecha": fecha or None,
        "tipo_intervencion": tipo_intervencion,
        "expediente": expediente or None,
        "observaciones": observaciones or None,
        "estado": estado,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }]
    errors = client.insert_rows_json(f"{PROJECT}.{DATASET}.dda_intervenciones", rows)
    if errors:
        raise RuntimeError(f"Error al insertar intervención: {errors}")
    return intervencion_id


def listar_intervenciones(dni: str) -> list[dict]:
    client = _client()
    dni_limpio = dni.replace(".", "").strip()
    query = """
        SELECT * FROM `admisiones-476215.Admisiones.dda_intervenciones`
        WHERE dni = @dni
        ORDER BY fecha DESC, created_at DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("dni", "STRING", dni_limpio)]
    )
    return [dict(r) for r in client.query(query, job_config=job_config).result()]


def listar_consultas(limit: int = 50) -> list[dict]:
    """Devuelve las últimas consultas registradas."""
    client = _client()
    query = f"""
        SELECT * FROM `{PROJECT}.{DATASET}.dda_consultas`
        ORDER BY fecha_consulta DESC
        LIMIT {limit}
    """
    return [dict(r) for r in client.query(query).result()]


def _imprimir_resultado(resultado: dict):
    if not resultado["encontrado"]:
        print(f"\n  DNI {resultado['dni']} no encontrado en las resoluciones.\n")
        return

    print(f"\n  Nombre: {resultado['nombre']}")
    print(f"  DNI:    {resultado['dni']}")
    print(f"  Resoluciones ({len(resultado['resoluciones'])}):")
    for r in resultado["resoluciones"]:
        fecha = r["fecha"].strftime("%d/%m/%Y") if r["fecha"] else "—"
        drive = f"https://drive.google.com/file/d/{r['drive_id']}" if r["drive_id"] else "—"
        print(f"    • {r['numero']}  ({fecha})  {drive}")
    print()


# --- CLI interactivo ---
if __name__ == "__main__":
    print("=" * 55)
    print("  Sistema DDA - Consulta por DNI")
    print("=" * 55)
    print("  Comandos: buscar | registrar | listar | salir")
    print()

    while True:
        cmd = input(">>> ").strip().lower()

        if cmd in ("salir", "exit", "q"):
            break

        elif cmd == "buscar":
            dni = input("  DNI: ").strip()
            resultado = buscar_por_dni(dni)
            _imprimir_resultado(resultado)

        elif cmd == "registrar":
            dni = input("  DNI: ").strip()
            canal = input("  Canal (whatsapp/email/presencial/telefono) [whatsapp]: ").strip() or "whatsapp"
            motivo = input("  Motivo: ").strip()
            notas = input("  Notas internas: ").strip()

            resultado = buscar_por_dni(dni)
            _imprimir_resultado(resultado)

            confirmar = input("  ¿Registrar esta consulta? (s/n): ").strip().lower()
            if confirmar == "s":
                consulta_id = registrar_consulta(dni, canal, motivo, notas)
                print(f"\n  Consulta registrada con ID: {consulta_id}\n")
            else:
                print("  Cancelado.\n")

        elif cmd == "listar":
            n = input("  Cuántas consultas mostrar? [20]: ").strip()
            n = int(n) if n.isdigit() else 20
            consultas = listar_consultas(n)
            if not consultas:
                print("  Sin consultas registradas.\n")
            else:
                print(f"\n  Últimas {len(consultas)} consultas:")
                for c in consultas:
                    fecha = c["fecha_consulta"].strftime("%d/%m/%Y %H:%M") if c["fecha_consulta"] else "—"
                    print(f"    [{fecha}] DNI {c['dni']} — {c['nombre']} — {c['canal']} — {c['motivo']}")
                print()

        else:
            print("  Comandos: buscar | registrar | listar | salir\n")
