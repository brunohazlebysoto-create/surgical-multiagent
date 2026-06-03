import uvicorn

if __name__ == "__main__":
    print("Iniciando Servidor Quirúrgico Pediátrico Multi-Agente...")
    print("Ingresa a http://localhost:8000 en tu navegador.")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
