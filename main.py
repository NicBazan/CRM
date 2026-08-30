from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import engine, Base, SessionLocal
import models, schemas
import httpx

from fastapi.middleware.cors import CORSMiddleware
# ==========================================
# CONFIGURACIÓN DE TELEGRAM Y MEMORIA
# ==========================================
TOKEN_TELEGRAM = "8746384392:AAHjStfWoxw7pyC0uGeYdEp0KSyUdjDp78U"

# Esta variable actúa como la "memoria RAM" para guardar los pedidos mientras chatean
carritos_clientes = {}

async def enviar_mensaje_telegram(chat_id, texto):
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto
    }
    async with httpx.AsyncClient() as client:
        respuesta = await client.post(url, json=payload)
        print(f"Estado de envío Telegram: {respuesta.status_code}")

# ==========================================
# INICIALIZACIÓN Y BASE DE DATOS
# ==========================================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
models.Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# RUTAS PRINCIPALES
# ==========================================
@app.get("/")
def leer_raiz():
    return {"mensaje": "¡El puente entre Python y la Base de Datos SQL está funcionando!"}

@app.post("/clientes/")
def crear_cliente(cliente: schemas.ClienteCrear, db: Session = Depends(get_db)):
    nuevo_cliente = models.Cliente(telefono=cliente.telefono, nombre=cliente.nombre)
    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)
    return nuevo_cliente

@app.get("/clientes/")
def leer_clientes(db: Session = Depends(get_db)):
    clientes = db.query(models.Cliente).all()
    return clientes

# ==========================================
# WEBHOOK DE TELEGRAM (EL CEREBRO DEL BOT)
# ==========================================
@app.post("/webhook")
async def recibir_mensaje_telegram(request: Request, db: Session = Depends(get_db)):
    body = await request.json()

    try:
        if "message" in body and "text" in body["message"]:
            mensaje_info = body["message"]
            chat_id = str(mensaje_info["chat"]["id"])
            texto_mensaje = mensaje_info["text"]
            nombre_cliente = mensaje_info["from"].get("first_name", "Cliente")

            print("\n========== NUEVO MENSAJE TELEGRAM ==========")
            print(f"🧑 Cliente:  {nombre_cliente}")
            print(f"💬 Mensaje:  {texto_mensaje}")
            print("===========================================\n")
            
            cliente_existente = db.query(models.Cliente).filter(models.Cliente.telefono == chat_id).first()
            
            if not cliente_existente:
                # 1. CLIENTE NUEVO
                nuevo_cliente = models.Cliente(
                    telefono=chat_id,
                    nombre=nombre_cliente,
                    estado="menu_principal",
                    ultimo_mensaje=texto_mensaje
                )
                db.add(nuevo_cliente)
                db.commit()
                
                mensaje_bienvenida = (
                    f"¡Hola {nombre_cliente}! Te comunicaste con Ciclo Confort 🛠️.\n\n"
                    "Por favor, ingresá el NÚMERO de la opción que buscás:\n"
                    "1 - Catálogo de Servicios\n"
                    "2 - Información Operativa\n"
                    "3 - Soporte"
                )
                await enviar_mensaje_telegram(chat_id, mensaje_bienvenida)

            else:
                # 2. CLIENTE EXISTENTE
                cliente_existente.ultimo_mensaje = texto_mensaje
                estado_actual = cliente_existente.estado
                
                # --- LÓGICA DEL MENÚ PRINCIPAL ---
                if estado_actual == "menu_principal":
                    if texto_mensaje == "1":
                        cliente_existente.estado = "menu_catalogo"
                        db.commit()
                        await enviar_mensaje_telegram(chat_id, "--- CATÁLOGO ---\n1 - Mantenimiento Aire Acondicionado ($15000)\n2 - Plomería ($8000)\n\nEscribí el número para agregar al carrito, o 'volver' para regresar.")
                        
                    elif texto_mensaje == "2":
                        await enviar_mensaje_telegram(chat_id, "Nuestros horarios son de Lunes a Viernes de 9 a 18hs. ⏰\n¿Te puedo ayudar con algo más? (1, 2 o 3)")
                        db.commit()
                        
                    else:
                        await enviar_mensaje_telegram(chat_id, "❌ Opción no reconocida. Por favor, ingresá 1, 2 o 3.")
                
                # --- LÓGICA DEL CATÁLOGO (CARRITO) ---
                elif estado_actual == "menu_catalogo":
                    # Le creamos un carrito vacío si todavía no tiene uno
                    if chat_id not in carritos_clientes:
                        carritos_clientes[chat_id] = []

                    if texto_mensaje == "1":
                        carritos_clientes[chat_id].append({"nombre": "Mantenimiento Aire", "precio": 15000})
                        await enviar_mensaje_telegram(chat_id, "✅ ¡Mantenimiento de Aire agregado!\nEscribí '1' o '2' para sumar más, '3' para ver el total, o 'volver'.")
                        
                    elif texto_mensaje == "2":
                        carritos_clientes[chat_id].append({"nombre": "Arreglo Plomería", "precio": 8000})
                        await enviar_mensaje_telegram(chat_id, "✅ ¡Arreglo de Plomería agregado!\nEscribí '1' o '2' para sumar más, '3' para ver el total, o 'volver'.")
                        
                    elif texto_mensaje == "3":
                        carrito_actual = carritos_clientes[chat_id]
                        if len(carrito_actual) == 0:
                            await enviar_mensaje_telegram(chat_id, "🛒 Tu carrito está vacío.")
                        else:
                            total = sum(item['precio'] for item in carrito_actual)
                            resumen = "🛒 *TU PEDIDO:*\n"
                            for item in carrito_actual:
                                resumen += f"- {item['nombre']}: ${item['precio']}\n"
                            resumen += f"\n💰 *TOTAL: ${total}*\n\n(Escribí 'confirmar' para enviar el pedido o 'volver' para cancelar)"
                            await enviar_mensaje_telegram(chat_id, resumen)
                            
                    elif texto_mensaje.lower() == "confirmar":
                        if len(carritos_clientes[chat_id]) > 0:
                            cliente_existente.estado = "esperando_direccion"
                            db.commit()
                            await enviar_mensaje_telegram(chat_id, "¡Excelente! Para procesar tu pedido, escribime tu dirección exacta:")
                        else:
                            await enviar_mensaje_telegram(chat_id, "❌ No podés confirmar un pedido vacío.")

                    elif texto_mensaje.lower() == "volver":
                        cliente_existente.estado = "menu_principal"
                        db.commit()
                        carritos_clientes[chat_id].clear()
                        await enviar_mensaje_telegram(chat_id, "Volvimos al inicio y vaciamos el carrito. Ingresá 1, 2 o 3.")
                        
                    else:
                        await enviar_mensaje_telegram(chat_id, "❌ Opción no reconocida. Escribí 1, 2, 3 o 'volver'.")
                
                # --- NUEVO ESTADO: ESPERANDO DIRECCIÓN ---
                elif estado_actual == "esperando_direccion":
                    direccion = texto_mensaje
                    cliente_existente.ultimo_mensaje = f"PEDIDO CONFIRMADO. Dirección: {direccion}"
                    cliente_existente.estado = "menu_principal"
                    db.commit()
                    
                    carritos_clientes[chat_id].clear()
                    await enviar_mensaje_telegram(chat_id, f"✅ ¡Pedido confirmado!\n📍 Dirección: {direccion}\nNos contactaremos a la brevedad.")

    except Exception as e:
        print("Error procesando el JSON:", e)

    return {"status": "ok"}