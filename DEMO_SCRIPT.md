# Relay demo recording

Record your screen and narrate in your own voice. Aim for **2 minutes 25 seconds**. Open the deployed frontend from the README in one browser tab. Open PowerShell 7 in another window and stage the commands below before starting.

## Setup

```powershell
$api = (Read-Host 'Paste the public backend URL from README').TrimEnd('/')
$run = [guid]::NewGuid().ToString('N').Substring(0,8)
function Send-DemoChat($session, $message, $simulate = '') {
    $headers = @{}
    if ($simulate) { $headers['X-Simulate-Failure'] = $simulate }
    $body = @{session_id=$session; message=$message} | ConvertTo-Json -Compress
    $res = Invoke-WebRequest "$api/chat" -Method Post -ContentType 'application/json' -Headers $headers -Body $body -SkipHttpErrorCheck
    "HTTP $($res.StatusCode)"
    $res.Content | ConvertFrom-Json | ConvertTo-Json -Depth 8
}
```

## 0:00–0:20 · Show the deployed UI

**On screen:** Show the public frontend address. Send `Remember that my codeword is Juniper 42. Reply only Ready.` Point to the reply and its source, model, latency, and token counts. If repeating a recording, use a fresh codeword and keep the first prompt handy.

**Narration:** “This is Relay, a React chat backed by FastAPI, LiteLLM, and SQLite. Each reply shows which model answered, whether it came from cache, how long it took, and how many input and output tokens that request used.”

## 0:20–0:45 · Show context and a cache hit

**On screen:** Ask `What was my codeword?` Point to the answer. Click **New chat** and send the exact first prompt again. Compare `LLM_CACHE` and the latency with the first turn, and mention that its text and token counts match.

**Narration:** “The second request includes the earlier turns, so the assistant remembers my codeword. A fresh session has no history. When I repeat the exact first prompt there, LiteLLM returns the same reply and token counts from cache.”

## 0:45–1:12 · Show health, chat, and persisted history

**On screen:** Run the following commands. Show the two loaded keys in health, live inference in the response, and the chronological user and assistant messages returned from SQLite.

```powershell
Invoke-RestMethod "$api/health" | ConvertTo-Json
Send-DemoChat "demo-$run" 'What is the capital of Portugal? Reply in one short sentence.'
Invoke-RestMethod "$api/sessions/demo-$run/messages" | ConvertTo-Json -Depth 8
```

**Narration:** “The health endpoint checks the database and the configured key pool. The history endpoint reads the messages and each assistant reply’s metadata from SQLite. The Railway volume is mounted at `/data`, so previous turns survive a service restart.”

## 1:12–1:45 · Demonstrate successful failover

**On screen:** Run the following. Highlight HTTP 200, the real reply, `key_2`, the Groq model, and `fallback_attempts: 1` in each result.

```powershell
Send-DemoChat "demo-429-$run" 'In one sentence, explain why the sky looks blue.' 'key_1=429'
Send-DemoChat "demo-500-$run" 'In one sentence, explain why the sky looks blue.' 'key_1=500'
```

**Narration:** “The failure header simulates a 429 and then a 500 for Gemini. Both requests get a real answer from Groq, which is key two. Simulation is limited to the request and bypasses the cache so we can see the fallback.”

## 1:45–2:13 · Demonstrate complete failure

**On screen:** Run the following. Show the 503 JSON response and the 404 for the failed session.

```powershell
Send-DemoChat "demo-down-$run" 'What causes a rainbow?' '*=429'
$missing = Invoke-WebRequest "$api/sessions/demo-down-$run/messages" -SkipHttpErrorCheck
"HTTP $($missing.StatusCode) $($missing.Content)"
```

**Narration:** “When every key fails, the backend returns a 503 with a clear JSON error. The failed turn never enters SQLite. The history lookup confirms the failed request did not create a session.”

## 2:13–2:25 · Close and upload

**On screen:** Return to the deployed frontend. Stop the recording after the closing line.

**Narration:** “Vercel serves the frontend, Railway hosts the API, and the public repository includes the Docker setup and backend tests.”

Upload the recording to YouTube as **Unlisted**, or upload it to Google Drive and choose **Anyone with the link → Viewer**. Open the video link in a signed-out or private browser window. The [assignment submission form](https://docs.google.com/forms/d/e/1FAIpQLSfaPS5_NliZuEjhYXppeafBrNM9u0hp-q-vT8vDuv9GU-0THA/viewform) has four project fields:

| Field | Value |
| --- | --- |
| GitHub Assignment Repo Link | [Public GitHub repository](https://github.com/Tanishq0211/lyftr-ai-chatbot) |
| Frontend URL | Production Vercel URL from the README |
| Backend API Base URL | Production Railway base URL from the README |
| Demo Video URL | The public or unlisted URL for your recording |
