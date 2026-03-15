Write src/pdf_loader.py that loads all PDF files from the /data 
folder into base64 encoded format ready to send to Gemini API. 
Each PDF should be tagged with its town name derived from the 
filename. Return a list of dicts with town_name and pdf_data fields. 
Also write a helper that downloads PDFs from a GCS bucket to /data 
if the folder is empty, using google-cloud-storage SDK.

Write src/context_builder.py that takes the loaded PDFs from 
pdf_loader.py and builds a Gemini API content array with all PDFs 
plus a detailed system prompt. The system prompt should:
- Give Penny a warm friendly persona as a CT town advisor
- Instruct her to always ground answers in the PDF data only, 
  never hallucinate numbers
- When comparing towns, always return a JSON block at the end 
  of the response in this format:
  {"chart_type": "bar", "title": "...", "x_labels": [...], 
   "datasets": [{"label": "...", "values": [...]}], 
   "highlight_towns": [...]}
- If no chart is relevant, omit the JSON block entirely

Write src/chart_parser.py that:
- Takes Gemini's raw text response as input
- Detects if a JSON chart block exists at the end using regex
- Parses it into a Python dataclass with fields: chart_type, 
  title, x_labels, datasets, highlight_towns
- Returns a tuple of (clean_text_response, chart_data_or_None)
- Handles malformed JSON gracefully without crashing
Include unit tests for 3 cases: response with chart, 
response without chart, response with malformed JSON.


Write src/live_agent.py using the google-genai Python SDK to:
- Initialize a Gemini Live API session with gemini-2.0-flash-exp
- Load all PDFs via context_builder.py at session start
- Accept microphone audio input using pyaudio, stream to Gemini
- Stream audio response back to speakers in real time
- INTERRUPT HANDLING: Implement full duplex audio — if user 
  speaks while Penny is talking, immediately stop current 
  audio playback, cancel current response, and process the 
  new input without any delay or awkward pause. Use Gemini 
  Live API's built-in VAD (Voice Activity Detection) for this.
- When interruption detected, emit an "interrupted" event 
  so the frontend can reset the UI state instantly
- Simultaneously extract chart JSON and town mentions from 
  text response using chart_parser.py
- Emit two callbacks:
  on_chart(chart_data) — when chart JSON is detected
  on_towns_mentioned(list_of_towns) — whenever town names 
  appear in Penny's response, even mid-sentence
- Expose: start_session(), send_text(query), stop_session()



Write app/main.py as a Streamlit app with this layout:

Header: "Penny — CT Town Advisor" with CT state outline icon

Left column (55%):
- Microphone toggle button with animated pulse when listening
- Visual waveform indicator when Penny is speaking
- INTERRUPT UI: when user speaks while Penny is talking, 
  show a "↩ Redirecting..." flash animation instantly
- Text input fallback for typing questions
- Chat history showing exchanges
- Status indicator with 4 states:
  🎙️ Listening... / 🤔 Thinking... / 🗣️ Speaking... / ↩ Redirecting...
- Suggested starter questions as clickable chips

Right column (45%):
- CT CHOROPLETH MAP using plotly — shows all CT towns in 
  light gray by default. When on_towns_mentioned callback 
  fires, animate mentioned towns to glow in accent color. 
  When two towns are compared, highlight both in different 
  colors simultaneously. Map updates mid-conversation 
  without page refresh using st.empty() placeholder.
- Below map: Plotly bar/line/radar chart that updates 
  when on_chart callback fires
- Both map and chart should animate smoothly on update 
  using plotly transition animations (duration: 500ms)

Use streamlit session state to:
- Persist PDF context across queries
- Track currently highlighted towns
- Track current agent state (listening/thinking/speaking/interrupted)


  Write infra/Dockerfile and infra/cloudbuild.yaml to deploy 
the Streamlit app to Google Cloud Run. Requirements:
- On container startup, download PDFs from GCS bucket to /data
- Launch Streamlit app on port 8080
- Set memory to 4Gi (PDFs in memory need space)
- Environment variables: GOOGLE_API_KEY, GCS_BUCKET_NAME, 
  GOOGLE_CLOUD_PROJECT
- cloudbuild.yaml should build image, push to Artifact Registry, 
  and deploy to Cloud Run in one command
- Include a README section with exact gcloud commands to deploy

Write demo_test.py that tests the full pipeline without voice 
using text queries. Run these 5 queries through the agent and 
print both Penny's response and any chart JSON returned:

1. "Is Wallingford a good town for a family with two kids?"
2. "Compare education spending across all CT towns and rank them"
3. "Which CT town has the lowest property tax rate?"
4. "How does Hartford public safety budget compare to Greenwich?"
5. "I earn $120k, which CT town gives me the best value for money?"

For each query print:
- Query number and text
- Penny's full text response  
- Chart JSON if present, or "No chart" if not
- Time taken in seconds





