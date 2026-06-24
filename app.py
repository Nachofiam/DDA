from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash
from dda import buscar_por_dni
from legajos import (
    add_presentacion, update_presentacion, list_presentaciones, delete_presentacion,
    add_novedad, list_novedades,
    add_cobro, list_cobros, delete_cobro,
    save_nombre, list_legajos,
    save_resolucion_extra, get_resoluciones_extra,
    TIPOS_PRESENTACION, ESTADOS_PRESENTACION, ESTADOS_NOVEDAD,
)

app = Flask(__name__)
app.secret_key = "dda-secret-2026"


@app.route("/")
def index():
    todos = list_legajos()
    return render_template("index.html", legajos=todos)


@app.route("/buscar", methods=["GET", "POST"])
def buscar():
    resultado = None
    dni = ""
    if request.method == "POST":
        dni = request.form.get("dni", "").strip()
        if dni:
            resultado = buscar_por_dni(dni)
    return render_template("buscar.html", resultado=resultado, dni=dni)


@app.route("/legajos")
def legajos():
    todos = list_legajos()
    return render_template("legajos.html", legajos=todos)


@app.route("/legajo/<dni>", methods=["GET", "POST"])
def legajo(dni):
    if request.method == "POST":
        seccion = request.form.get("seccion")

        if seccion == "presentacion":
            add_presentacion(
                dni,
                fecha=request.form.get("fecha", ""),
                tipo=request.form.get("tipo", ""),
                descripcion=request.form.get("descripcion", ""),
                expediente=request.form.get("expediente", ""),
                estado=request.form.get("estado", "Pendiente"),
            )
            flash("Presentación registrada.", "success")

        elif seccion == "update_presentacion":
            update_presentacion(
                dni,
                doc_id=request.form.get("doc_id"),
                fecha=request.form.get("fecha", ""),
                tipo=request.form.get("tipo", ""),
                descripcion=request.form.get("descripcion", ""),
                expediente=request.form.get("expediente", ""),
                estado=request.form.get("estado", "Pendiente"),
            )
            flash("Presentación actualizada.", "success")

        elif seccion == "novedad":
            add_novedad(
                dni,
                texto=request.form.get("texto", ""),
                estado=request.form.get("estado", ""),
            )
            flash("Novedad registrada.", "success")

        elif seccion == "cobro":
            try:
                monto = float(request.form.get("monto", 0) or 0)
                pagado = float(request.form.get("pagado", 0) or 0)
                add_cobro(
                    dni,
                    concepto=request.form.get("concepto", ""),
                    monto=monto,
                    pagado=pagado,
                )
                flash("Cobro registrado.", "success")
            except ValueError:
                flash("Monto o Pagado deben ser números.", "error")

        elif seccion == "delete_presentacion":
            delete_presentacion(dni, request.form.get("doc_id"))
            flash("Presentación eliminada.", "success")

        elif seccion == "delete_cobro":
            delete_cobro(dni, request.form.get("doc_id"))
            flash("Cobro eliminado.", "success")

        elif seccion == "resolucion_extra":
            save_resolucion_extra(
                dni,
                numero=request.form.get("numero"),
                tipo=request.form.get("tipo", ""),
                plazo=request.form.get("plazo", ""),
                partido=request.form.get("partido", ""),
            )
            flash("Resolución actualizada.", "success")

        return redirect(url_for("legajo", dni=dni))

    datos_bq = buscar_por_dni(dni)
    if datos_bq["encontrado"] and datos_bq["nombre"]:
        save_nombre(dni, datos_bq["nombre"])
    if request.args.get("check"):
        cant = len(datos_bq.get("resoluciones", []))
        flash(f"Verificación completada. Se encontraron {cant} resolución/es para este DNI.", "success")
    if datos_bq["encontrado"]:
        extras = get_resoluciones_extra(dni)
        for r in datos_bq["resoluciones"]:
            extra = extras.get(r["numero"], {})
            r["tipo"] = extra.get("tipo", "")
            r["plazo"] = extra.get("plazo", "")
            r["partido"] = extra.get("partido", "")
    presentaciones = list_presentaciones(dni)
    novedades = list_novedades(dni)
    cobros = list_cobros(dni)

    return render_template(
        "legajo.html",
        datos_bq=datos_bq,
        presentaciones=presentaciones,
        novedades=novedades,
        cobros=cobros,
        dni=dni,
        tipos_presentacion=TIPOS_PRESENTACION,
        estados_presentacion=ESTADOS_PRESENTACION,
        estados_novedad=ESTADOS_NOVEDAD,
        today=date.today().isoformat(),
    )



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
