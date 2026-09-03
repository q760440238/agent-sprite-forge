# Debug Session: map-controls-state

Status: OPEN

## Symptom

When selecting a map background, the object category and NPC type controls appear selectable or retain an incorrect state in production.

## Hypotheses

1. The public endpoint serves an outdated frontend asset or process.
2. Map-mode state only disables controls but does not correctly reflect their values.
3. The deployed frontend differs from the local source.
4. Nginx routing or cache behavior serves a stale resource.

## Evidence

- The production service started from `/opt/agent-sprite-forge` at `2026-08-26 17:58:26 CST`; systemd reports it as active.
- The production `webui/static/app.js`, `index.html`, and `server.py` hashes match the deployed source. Nginx has no cache directives for this site.
- The production JavaScript sets `spriteOpts.hidden` and `frameOpts.hidden` when `kind === "map"`.
- The integrated browser selector changed the select value without dispatching the native `change` event. Its accessibility snapshot therefore showed stale Sprite controls.
- Dispatching a native `change` event in the production page produced `spriteOpts.hidden=true`, `frameOpts.hidden=true`, `target.disabled=true`, and `npcRole.disabled=true`.
- A separate Puppeteer Chrome run could not start because the required local Chrome binary is unavailable.

## Conclusion

The production server is updated and restarted correctly. The observed stale state is not caused by the deployed service. A real browser must reload the current static JavaScript and use the native select change event; a hard reload rules out a cached older asset.
