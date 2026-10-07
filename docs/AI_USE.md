# Use of AI

NASA Space Apps allows AI-assisted work when every tool is named, the prompts are explained and the
team's own work is clear. This file records all of it for SafeSol (Team Cosmic84).

## Tools

| Tool | What it was used for | What the team did |
|---|---|---|
| Anthropic Claude (claude.ai) | Brainstorming challenge ideas; first drafts of the code in `src/` and `web/`, the tests, the documentation and the deployment files (`deploy/`); explaining errors while we set up data and the server | Chose the challenge and the solar storm shelter idea; reviewed and ran all code; ran every test; downloaded and processed the NASA data ourselves; checked the results against the Build Guide; deployed the app on our own server; recorded the video |
| OpenAI ChatGPT | First draft of a functional requirements and methodology document for the Martian Map challenge | Reviewed it, compared it with the Build Guide and used it as input for the final design |

## Main prompts (summary)

- "Suggest original app ideas for the 2026 Space Apps challenges, especially about humans on the Moon and Mars."
- "Build challenge 11, Interplanetary Survival Guide: Martian Map, following the Build Guide architecture, with a Solar Storm Shelter Finder."
- "Check our project against every requirement in the Build Guide for challenge 11 and fix what is missing."
- "Explain step by step how to download real NASA data (terrain and DONKI solar storms) and deploy the app on our VPS."

## What AI did not do

- No AI model runs inside SafeSol. Every number in the app (slope, energy, routes, shelter shielding,
  storm escape) comes from deterministic code in `src/compute`, checked by 17 unit tests on terrain
  with known answers.
- AI did not produce or change any data. The terrain (NASA MRO CTX) and the storm events (NASA DONKI)
  were downloaded by the team from the original sources; see `docs/DATA_SOURCES.md`.
- No AI-generated images, and no NASA logos.
