# Mundial 2026 · Dashboard auto-actualizado

Seguimiento del Mundial de Fútbol 2026 (USA · México · Canadá · 11 jun – 19 jul 2026) que se **actualiza solo cada día** desde Wikipedia. Sin tocar nada manualmente.

> Demo URL (después del despliegue): `https://<tu-usuario>.github.io/mundial-2026/`

## Cómo funciona

```
┌──────────────┐    cron diario    ┌──────────────────┐    push    ┌──────────────┐
│  Wikipedia   │ ───────────────▶  │  GitHub Action   │ ─────────▶ │   Repo       │
│  (Group A–L) │                   │  Python scraper  │            │   data.json  │
└──────────────┘                   └──────────────────┘            └──────┬───────┘
                                                                          │ GitHub Pages
                                                                          ▼
                                                                   ┌──────────────┐
                                                                   │   index.html │
                                                                   │   (lee data) │
                                                                   └──────────────┘
                                                                          ▲
                                                                          │ HTTPS
                                                                          │
                                                                   👤 Tú abres la URL
```

Cada día a las **07:00 UTC** (09:00 Madrid), GitHub Actions:
1. Lanza un runner Ubuntu gratuito
2. Ejecuta `python scripts/update_results.py` (scrapea las 12 páginas de grupos + la de eliminatorias en Wikipedia)
3. Si hay cambios → actualiza `data.json` y `mundial-2026.html`, hace commit y push
4. GitHub Pages publica la versión nueva en ~30 s

Tú abres la URL → ves los resultados del día anterior automáticamente.

## Estructura del repo

```
.
├── index.html                    # App web (lee data.json)
├── data.json                     # Datos: equipos, grupos, calendario, resultados auto
├── mundial-2026.html             # Versión single-file para compartir offline
├── README.md
├── requirements.txt              # Dependencias Python del scraper
├── .github/
│   └── workflows/
│       └── daily-update.yml      # GitHub Action — cron diario + manual trigger
└── scripts/
    ├── update_results.py         # Scrapea Wikipedia → escribe data.json["liveResults"]
    └── build_single_file.py      # Bundlea data.json dentro de mundial-2026.html
```

## Despliegue en 5 pasos

### 1. Crear el repo en GitHub

- Entra en https://github.com, *Sign in* (o crea cuenta gratis)
- Esquina superior derecha → `+` → **New repository**
- Nombre sugerido: `mundial-2026`
- **Public** (necesario para GitHub Pages gratis)
- Marca "Add a README" para que se cree con un commit inicial
- *Create repository*

### 2. Subir los archivos

Tres formas, elige la que prefieras:

**Opción A — Web (más fácil)**
1. En el repo recién creado, click en `Add file` → `Upload files`
2. Arrastra **TODO** el contenido de esta carpeta `github-repo/` (excepto la propia carpeta `.github` que GitHub web no acepta arrastrar — hazlo aparte)
3. Para `.github/workflows/daily-update.yml`: en el repo, `Add file` → `Create new file` → escribe la ruta exacta `.github/workflows/daily-update.yml` y pega el contenido
4. Commit changes

**Opción B — GitHub Desktop**
1. Instala https://desktop.github.com
2. *Clone* el repo a tu PC
3. Copia los archivos de `github-repo/` a la carpeta clonada
4. En GitHub Desktop: commit + push

**Opción C — Línea de comandos** (si tienes git instalado)
```powershell
cd "C:\Users\gregorio.carazo\OneDrive - Accenture\Mundial 2026\github-repo"
git init
git remote add origin https://github.com/<tu-usuario>/mundial-2026.git
git branch -M main
git add .
git commit -m "Initial setup"
git push -u origin main
```

### 3. Activar GitHub Pages

- En el repo → **Settings** → **Pages** (menú izquierdo)
- *Source:* **Deploy from a branch**
- *Branch:* **main** / **/ (root)** → Save
- Espera ~1 min. Volverá a aparecer la URL: `https://<tu-usuario>.github.io/mundial-2026/`

### 4. Permitir que la Action haga commits

- En el repo → **Settings** → **Actions** → **General**
- Baja hasta *Workflow permissions*
- Marca **Read and write permissions** → Save

Sin esto, la Action no podrá hacer push de los cambios diarios.

### 5. Dispara la primera actualización manual

- En el repo → **Actions** (pestaña superior)
- Click en **Update World Cup results** (panel izquierdo)
- *Run workflow* → *Run workflow* (botón verde)
- En ~30 s la Action habrá corrido. Mientras no haya partidos jugados, no harás push (no hay cambios). Cuando empiece el torneo, cada ejecución diaria publicará los resultados nuevos.

Listo. La Action está configurada con `cron: "0 7 * * *"` (07:00 UTC = 09:00 Madrid en verano) → se ejecuta sola cada día.

## Cómo coexisten resultados auto + manuales

El dashboard mantiene **dos capas separadas**:

| Capa | Origen | Persistencia | Casos de uso |
|---|---|---|---|
| **autoResults** | `data.json.liveResults` (auto) | En el repo, regenerada cada día | Resultados oficiales del Mundial |
| **userResults** | localStorage del navegador | Por usuario y dispositivo | Predicciones, simulaciones, quinielas privadas |

**Reglas de merge:**
- Vista por defecto: `userResults` se superpone a `autoResults`
- *Reset* en el footer → borra solo tus userResults; los oficiales siguen ahí
- *Exportar* → solo userResults (lo oficial está en el repo)

Esto significa que **cuando alguien abre la URL, ve los resultados oficiales sin haber tocado nada**. Si además marcó sus propias predicciones, las ve por encima.

## Compatibilidad y límites del scraper

El parser detecta:
- ✅ `{{#invoke:football box|main|...}}` (formato moderno usado en 2026)
- ✅ `{{Football box}}` (formato clásico, usado en mundiales anteriores)
- ✅ Score embebido en `{{score link|...|2–1}}` o como string directo
- ✅ Goleadores con `{{goal|NN}}` y minutos
- ❌ Penaltis en tiempo extra detallados — solo se registra el resultado de la tanda como score
- ❌ Tarjetas y sustituciones (no se necesitan para el dashboard)

Validado contra:
- 2022 World Cup Group A (real, 6/6 partidos con goleadores) → OK
- 2026 World Cup Group A (preparado, 6/6 partidos sin resultado aún) → OK

Si Wikipedia cambia el formato durante el torneo, el script muestra `0 played` y no rompe nada. Solo habría que ajustar el parser; el resto sigue funcionando.

## Mantenimiento

- **No necesitas tocar nada** durante el torneo. La Action se ejecuta sola.
- Si quieres forzar una actualización fuera de cron: *Actions* → *Run workflow*.
- Si Wikipedia cambia el formato de un campo, abre un issue en este repo y editaré `update_results.py`.

## Compartir el dashboard

- **URL para los demás:** `https://<tu-usuario>.github.io/mundial-2026/`
- **Archivo offline:** descarga `mundial-2026.html` del repo (versión single-file con datos embebidos del último build de la Action)

## Coste

0 €. GitHub Pages, GitHub Actions y el runner Ubuntu son gratuitos hasta 2 000 min/mes (esto consume ~30 s/día = 15 min/mes).
