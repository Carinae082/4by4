# Pygame Stage 1 Render Deploy

This folder is prepared for deploying the Pygame assignment to Render as a Static Site through pygbag.

## Render settings

- Service type: Static Site
- Build command: `python -m pip install -r requirements.txt && python -m pygbag --build game`
- Publish directory: `game/build/web`

## File layout

```txt
.
├── game/
│   └── main.py
├── requirements.txt
├── render.yaml
└── README.md
```

Push this folder's contents to GitHub, then create a new Render Static Site from that repository.
