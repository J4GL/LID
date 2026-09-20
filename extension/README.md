# LID — Chrome extension

Send `.torrent` files and magnet links from Chrome to your LID server,
over direct or proxy. Manifest V3, no content scripts, narrow permissions.

## Install (unpacked)

1. Open `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** and select this `extension/` folder.
3. Open the extension's **Options** (or click its toolbar icon, then
   **Settings**) and check the server address
   (default `http://192.168.1.29:8000/`). **Save**, then **Test connection**.

## Use

- Click a `.torrent` link or button: Chrome's download is cancelled and a
  route picker opens (**Direct** / **Proxy**). On the first torrent from a
  new site, Chrome asks for one-click access to that site so the extension
  can fetch the file (cookies included for private trackers).
- Right-click any link and choose **Send to LID**: works for `magnet:` links
  and direct `.torrent` URLs.
- A notification confirms each addition or explains the failure (server
  unreachable, proxy unavailable, torrent already present…).

## Notes

- The server address can be changed in Options; granting the new origin is
  requested on save.
- Files Chrome cannot hand over (e.g. `blob:` downloads) are left to
  download normally: drop the `.torrent` file into the LID dashboard instead.
- Left-clicking a `magnet:` link still goes to the OS handler; use
  right-click → **Send to LID**.

## Tests

```sh
node --test tests/extension-capture.test.mjs tests/extension-client.test.mjs tests/extension-worker.test.mjs
```

Specs: `SPEC/extension/capture.md`, `SPEC/extension/client.md`,
`SPEC/extension/worker.md`.
