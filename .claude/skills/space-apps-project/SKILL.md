---
name: space-apps-project
description: Scaffold and manage a NASA Space Apps 2026 project. Use when building any of the 14 challenges, wiring the offline-first data cache, or preparing the judging submission.
license: Apache-2.0
metadata:
  author: SpaceApps-Bangladesh
  version: "1.0"
---
# Space Apps 2026 project
## When to use
Any Space Apps 2026 build. Enforces offline-first caching, cited data, an OSI
license, no under-18 likeness, and AI-use disclosure.
## Steps
1. Create the repo with LICENSE (Apache-2.0), README, cache/, demo_fixtures/,
   src/{acquire,compute,agents,api}, web/, docs/AI_USE.md.
2. Wire data through src/acquire/safe.py. Write every response to cache/.
3. Keep deterministic science in src/compute. Agents orchestrate and explain only.
4. Before the demo, run with OFFLINE=1 and record a 240-second video.
5. Fill the NASA project page: summary, demo video, details, repo link, use of AI,
   NASA data sources, references.
## Guardrails
- Cite every dataset with an id and a URL.
- Name every AI tool used and record the prompts in docs/AI_USE.md.
- The repository must be public and openly licensed.
