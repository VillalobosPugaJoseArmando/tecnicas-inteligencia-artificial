# Tutor Inteligente

Página web tipo Duolingo, pero con un chatbot tutor de materias de la Facultad de Informática Mazatlán (FIMAZ-UAS). Los alumnos se registran, chatean con la IA, ganan XP, suben de nivel, mantienen una racha de días seguidos y compiten en un ranking público.

Materias disponibles por ahora: **Inteligencia Artificial**, **Base de Datos** y **Redes y Cableado**.

## Qué hace

- Registro e inicio de sesión con usuario y contraseña.
- Chat con un tutor de IA que corre **de forma local** con [Ollama](https://ollama.com) (modelo `qwen3.5:4b`), sin API key y sin costo.
- Preguntas sugeridas por materia, retos y mini exámenes.
- Apoyo con artículos de Wikipedia en español para las preguntas de concepto.
- XP (+10 por cada reto acertado), niveles (cada 50 XP), racha diaria y ranking.

## Requisitos

- Python 3.10 o superior
- Git
- [Ollama](https://ollama.com/download)
- Unos 4 GB libres para el modelo. Funciona solo con CPU, pero las respuestas tardan más que en una computadora con GPU.

## Instalación

Clona el repositorio:

```
git clone https://github.com/VillalobosPugaJoseArmando/tecnicas-inteligencia-artificial.git
cd tecnicas-inteligencia-artificial/tutor-inteligente
```

### Windows (PowerShell)

1. Instala Python desde [python.org](https://www.python.org/downloads/) (marca la casilla "Add Python to PATH") y Ollama desde [ollama.com/download](https://ollama.com/download).
2. Crea el entorno virtual e instala las dependencias:

```
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea el script de activación, ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a intentar.

3. Descarga el modelo:

```
ollama pull qwen3.5:4b
```

4. Inicia la app:

```
python app.py
```

### Linux

1. Instala Python, Git y Ollama.
   - Arch / CachyOS: `sudo pacman -S python git ollama`
   - Debian / Ubuntu: `sudo apt install python3 python3-venv python3-pip git` y luego Ollama con `curl -fsSL https://ollama.com/install.sh | sh`
2. Activa el servicio de Ollama (si tu instalación no lo hizo sola):

```
sudo systemctl enable --now ollama
```

3. Crea el entorno virtual e instala las dependencias:

```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Si usas **fish**, activa con `source venv/bin/activate.fish`.

4. Descarga el modelo y arranca la app:

```
ollama pull qwen3.5:4b
python app.py
```

### macOS

1. Instala Python, Git y Ollama (con [Homebrew](https://brew.sh) o desde [ollama.com/download](https://ollama.com/download)):

```
brew install python git
brew install --cask ollama
```

Abre la app de Ollama una vez para que el servicio quede corriendo.

2. Crea el entorno virtual e instala las dependencias:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Descarga el modelo y arranca la app:

```
ollama pull qwen3.5:4b
python app.py
```

En versiones recientes de macOS, el puerto 5000 puede estar ocupado por AirPlay. Si ves ese error, desactiva "Receptor AirPlay" en Ajustes del Sistema o cambia el puerto al final de `app.py` (`app.run(debug=True, port=5001)`).

## Uso

1. Abre <http://localhost:5000> en el navegador.
2. Regístrate con un usuario y una contraseña (mínimo 6 caracteres).
3. Elige una materia y pregúntale al tutor, o pídele un reto.

La base de datos (SQLite) se crea sola en la carpeta `instance/` la primera vez que corres la app.

## Configuración

- **Modelo:** cambia la constante `MODELO` al inicio de `app.py`. Si tu equipo es lento, prueba uno más pequeño, por ejemplo `qwen3.5:2b` o `llama3.2:3b`, y descárgalo antes con `ollama pull`.
- **Clave secreta:** cambia el valor de `SECRET_KEY` en `app.py` antes de publicar la app en un servidor real.

## Estructura del proyecto

```
.
├── app.py              # backend (Flask, base de datos, chat con Ollama)
├── requirements.txt    # dependencias de Python
└── templates/          # plantillas HTML (base, login, ranking, inicio, chat)
```

## Problemas comunes

- **"No pude conectar con Ollama":** el servicio no está corriendo. En Linux usa `sudo systemctl start ollama`; en Windows y macOS abre la app de Ollama.
- **"Falta el modelo":** corre `ollama pull qwen3.5:4b`.
- **Las respuestas tardan mucho:** es normal en CPU. Prueba un modelo más pequeño.

## Limitaciones conocidas

- El XP se otorga cuando el modelo escribe una etiqueta especial, así que un modelo pequeño puede olvidarla y un alumno podría intentar engañarlo. Hace falta validarlo mejor si el ranking se usa en serio.
- En CPU solo se atiende una respuesta a la vez, así que varios alumnos simultáneos harían cola.
