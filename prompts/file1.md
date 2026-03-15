Prompt 1 

Create a Python project structure for "Penny — CT Town Advisor", 
a voice agent for the Gemini Live Agent Challenge hackathon.

Tech stack:
- Frontend: Streamlit with custom CSS/HTML
- Backend: FastAPI
- Voice: Gemini Live API
- Charts: Plotly
- Data: Structured JSON (no vector DB)
- Hosting: Google Cloud Run

Folder structure:
/data
  - wallingford.json
  - north_haven.json  
  - cheshire.json
/src
  - context_builder.py
  - live_agent.py
  - chart_parser.py
  - tax_calculator.py
/app
  - main.py (Streamlit frontend)
  - styles.css
/api
  - main.py (FastAPI backend)
/infra
  - Dockerfile
  - cloudbuild.yaml
requirements.txt
.env.example
README.md

Include requirements.txt with:
google-genai, fastapi, uvicorn, streamlit, plotly, 
python-dotenv, pyaudio, websockets, httpx

Create .env.example with:
GOOGLE_API_KEY=
GOOGLE_CLOUD_PROJECT=
GCS_BUCKET_NAME=

Prompt 2 
Write a one-time script src/extract_town_data.py that:
- Takes a PDF file path and town name as arguments
- Sends the entire PDF to Gemini Vision in one shot
- Asks Gemini to extract the following into structured JSON:

{
  "town": "Wallingford",
  "budget_year": "2025-26",
  "total_budget": 197000000,
  "mill_rate": 28.52,
  "median_home_price": 475000,
  "population": 45000,
  "persona": "The Education Champion",
  "persona_description": "2-3 sentence description",
  "departments": {
    "education": {"amount": 0, "percent": 0},
    "public_safety": {"amount": 0, "percent": 0},
    "infrastructure": {"amount": 0, "percent": 0},
    "debt_service": {"amount": 0, "percent": 0},
    "health_services": {"amount": 0, "percent": 0},
    "administration": {"amount": 0, "percent": 0}
  },
  "key_facts": ["fact1", "fact2", "fact3"],
  "strengths": ["strength1", "strength2"],
  "weaknesses": ["weakness1", "weakness2"]
}

- If a field is not found set it to null
- Save output as /data/{town_name}.json
- Run for all 3 towns: Wallingford, North Haven, Cheshire

Include clear instructions in comments on how to run this 
script for each town PDF.


Prompt 3
Write src/context_builder.py that:
- Loads all 3 town JSON files from /data folder
- Builds a system prompt for Penny with:

PERSONA:
Penny is a warm, knowledgeable CT town advisor who helps 
people decide where to live. She speaks in short friendly 
sentences. She never makes up numbers — only uses data 
from the town JSONs. She always grounds answers in real 
budget data.

RESPONSE FORMAT:
Penny always returns responses as JSON with two fields:
{
  "voice_response": "what Penny says out loud — keep under 
                     3 sentences, conversational",
  "ui_update": {
    "active_town": "town name or null",
    "chart": {
      "chart_type": "bar|pie|radar|none",
      "title": "...",
      "x_labels": [...],
      "datasets": [{"label": "...", "values": [...]}]
    },
    "show_listings": true|false,
    "show_calculator": true|false,
    "highlight_towns": ["town1", "town2"]
  }
}

- Expose build_context() that returns the full Gemini 
  content array ready to use
- Expose get_town_data(town_name) for direct data access


Prompt 4

Write two modules:

src/chart_parser.py:
- Takes Penny's raw JSON response string
- Parses it into voice_response and ui_update fields
- Returns (voice_text, ui_update_dict) tuple
- Handles malformed JSON gracefully — if parsing fails,
  treat entire response as voice_response with no ui_update
- Validates chart data has required fields before returning

src/tax_calculator.py:
- Takes home_price and mill_rate as inputs
- Calculates:
  annual_tax = (home_price / 1000) * mill_rate
  monthly_tax = annual_tax / 12
  monthly_total = monthly_mortgage + monthly_tax
- Returns formatted dict with all values
- Expose calculate(home_price, town_name) that looks up 
  mill rate from town JSON automatically

Prompt 5

  Write src/live_agent.py using google-genai Python SDK:

SETUP:
- Initialize Gemini Live API session with gemini-2.0-flash-exp
- Load context from context_builder.py at session start
- Use model config: response_modalities=["AUDIO", "TEXT"]

AUDIO INPUT:
- Capture microphone using pyaudio
- Stream audio chunks to Gemini Live API in real time
- Sample rate: 16000hz, chunk size: 1024

AUDIO OUTPUT:
- Stream Gemini audio response to speakers in real time
- Sample rate: 24000hz

INTERRUPT HANDLING:
- Implement full duplex audio using Gemini Live API's 
  built-in VAD (Voice Activity Detection)
- When user speaks while Penny is talking:
  1. Immediately stop audio playback
  2. Cancel current response
  3. Process new input without delay
  4. Emit on_interrupted() callback for frontend UI update

CALLBACKS:
- on_voice_response(text) — full text of Penny's response
- on_ui_update(ui_update_dict) — parsed chart/map data
- on_state_change(state) — "listening"|"thinking"|
  "speaking"|"interrupted"
- on_interrupted() — fires when user interrupts Penny

INTERFACE:
- start_session() — initialize and start listening
- send_text(query) — for text input fallback  
- stop_session() — clean shutdown

Prompt 6
Write app/main.py as a Streamlit app for Penny — CT Town Advisor.

STYLING:
Inject custom CSS via st.markdown for:
- Dark theme: background #0a0e1a, accent #00d4ff
- Persona card styling with border glow effect
- Listing card styling
- Doorway animation using CSS keyframes:
  @keyframes doorOpen — two panels slide apart left/right
  revealing listings cards behind them
- Smooth chart transitions
- Microphone button pulse animation when listening

LAYOUT:

Header:
- "Penny" logo + "CT Town Advisor" subtitle
- Status pill: 🎙️ Listening | 🤔 Thinking | 🗣️ Speaking | ↩️ Redirecting

Left column (55%):
- Persona card for active town showing:
  town name, persona title, persona description
  3 key stats: mill rate, total budget, education %
- Microphone toggle button with pulse animation
- Text input fallback
- Chat history (last 5 exchanges)
- Starter question chips:
  "Best town for families?"
  "Compare education spending"
  "Show homes in North Haven"
  "What's my tax on a $450k home?"

Right column (45%):
- Plotly chart (bar/pie/radar) updates on ui_update
- DOORWAY ANIMATION: 
  st.empty() placeholder
  When show_listings=True in ui_update:
  Play doorway CSS animation then reveal 3 listing cards
  Each card shows: address, price, beds/baths, town name
  When show_listings=False: hide listings, show chart
- Tax calculator panel (shows when show_calculator=True):
  st.slider for home price $100k-$1M
  Dropdown to select town
  st.metric showing annual tax, monthly tax, total monthly cost
  Updates in real time as slider moves

STATE MANAGEMENT:
Use st.session_state for:
- active_town
- current_chart_data  
- show_listings
- show_calculator
- agent_state (listening/thinking/speaking/interrupted)
- chat_history

Prompt 7


Write infra/Dockerfile and infra/cloudbuild.yaml to deploy 
Penny to Google Cloud Run.

Dockerfile:
- Base image: python:3.11-slim
- Install system deps: portaudio19-dev (for pyaudio), ffmpeg
- Install Python requirements
- Copy app files
- Expose port 8080
- CMD: streamlit run app/main.py --server.port=8080 
  --server.address=0.0.0.0

cloudbuild.yaml:
- Step 1: Build Docker image
- Step 2: Push to Artifact Registry
- Step 3: Deploy to Cloud Run with:
  memory: 2Gi
  cpu: 2
  min-instances: 1 (so no cold start during demo)
  env vars: GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT

README deployment section with exact commands:
1. gcloud auth login
2. gcloud config set project YOUR_PROJECT
3. gcloud builds submit --config infra/cloudbuild.yaml
4. gcloud run services describe penny-ct-advisor --format url

Also write a local development quickstart:
1. Clone repo
2. cp .env.example .env and fill in keys
3. python src/extract_town_data.py (one time)
4. streamlit run app/main.py

Prompt 8

Write demo_test.py that tests the full pipeline via text 
(no voice) and prints results for all 5 demo scenarios:

Scenario 1 — Opening question:
"Which of these three CT towns is best for a family with kids?"
Expected: Penny recommends a town, persona card data returned,
bar chart of education spending across 3 towns

Scenario 2 — Comparison:
"Compare education spending across Wallingford, 
North Haven and Cheshire"
Expected: Chart data with all 3 towns, ranking

Scenario 3 — Listings trigger:
"Show me homes in North Haven"
Expected: show_listings=True in ui_update, 
doorway animation should trigger

Scenario 4 — Tax calculator:
"If I buy a $500k house in Wallingford what's my annual tax?"
Expected: show_calculator=True, calculated tax values returned

Scenario 5 — Interruption simulation:
Send "Tell me about Cheshire's budget in detail"
After 1 second send "actually what about North Haven instead"
Expected: second query overrides first cleanly

For each scenario print:
- Scenario name
- Query sent
- Penny's voice response
- ui_update JSON
- Pass/Fail based on expected output
- Response time in seconds

Prommpt 9 
Write a one-time script src/generate_avatars.py that uses 
Gemini 2.0 Flash image generation to create avatar illustrations 
for each town persona.

For each town generate one avatar using this prompt template:
"A friendly, warm, flat illustration avatar character 
representing a CT town persona called '{persona_name}'. 
{persona_description}. Clean flat design style, 
vibrant colors, transparent background, 
circular framing, professional illustration."

Generate avatars for:

1. Wallingford — "The Education Champion"
   Description: Academic, aspirational, graduation theme,
   deep blue and gold colors

2. North Haven — "The Balanced Budgeter"  
   Description: Steady, reliable, balanced scale theme,
   forest green and cream colors

3. Cheshire — "The Safe Haven"
   Description: Safe, community-oriented, shield and 
   nature theme, navy and amber colors

Save each avatar as:
/app/assets/wallingford_avatar.png
/app/assets/north_haven_avatar.png
/app/assets/cheshire_avatar.png

Print confirmation and file size after each save.
Only needs to run once — add a check to skip generation 
if file already exists.