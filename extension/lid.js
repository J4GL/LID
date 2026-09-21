// Minimal LID API client for the extension. The fetch implementation is
// injected so the logic stays unit-testable (EXT-CLI-001).

export const MAX_TORRENT_BYTES = 10 * 1024 * 1024;

export class LidError extends Error {
  constructor(code, message = "", data = null) {
    super(message || code);
    this.name = "LidError";
    this.code = code;
    this.data = data;
  }
}

export class LidClient {
  constructor(serverUrl, fetchImpl = fetch) {
    this.base = String(serverUrl || "").replace(/\/+$/, "");
    // Window.fetch requires its Window receiver: calling it back as a method
    // (this.fetch) throws "Illegal invocation" in browsers. The closure keeps
    // the injected implementation directly callable. (Node's fetch tolerates
    // detached calls, so only a receiver-checking double catches this.)
    this.fetch = (...args) => fetchImpl(...args);
    this.token = "";
  }

  async bootstrap() {
    let response;
    try {
      response = await this.fetch(`${this.base}/api/bootstrap`);
    } catch {
      throw new LidError("server_unreachable");
    }
    if (!response.ok) throw new LidError("server_unreachable");
    const data = await response.json();
    this.token = data.token || "";
    if (!this.token) throw new LidError("server_unreachable");
    return data;
  }

  async request(path, options = {}, retried = false) {
    if (!this.token) await this.bootstrap();
    let response;
    try {
      response = await this.fetch(`${this.base}${path}`, {
        ...options,
        headers: { ...(options.headers || {}), "X-P2P-Token": this.token },
      });
    } catch {
      throw new LidError("server_unreachable");
    }
    if (response.status === 403 && !retried) {
      await this.bootstrap();
      return this.request(path, options, true);
    }
    let data = {};
    try {
      data = await response.json();
    } catch {
      throw new LidError("unexpected_response");
    }
    if (!response.ok) {
      throw new LidError(
        data.code || "unexpected_response",
        data.detail || "",
        data,
      );
    }
    return data;
  }

  async uploadTorrent(bytes, filename, mode) {
    const size = bytes?.byteLength ?? bytes?.length ?? 0;
    if (size > MAX_TORRENT_BYTES) throw new LidError("file_too_large");
    const form = new FormData();
    form.append("mode", mode);
    form.append(
      "files",
      new Blob([bytes], { type: "application/x-bittorrent" }),
      filename,
    );
    let data;
    try {
      data = await this.request("/api/torrents/files", {
        method: "POST",
        body: form,
      });
    } catch (error) {
      // LID answers 409 with per-file results when every file fails.
      const [failed] = error?.data?.results || [];
      if (error instanceof LidError && failed && !failed.ok) {
        throw new LidError(
          failed.error_code || "unexpected_response",
          failed.error || "",
        );
      }
      throw error;
    }
    const [result] = data.results || [];
    if (!result?.ok) {
      throw new LidError(
        result?.error_code || "unexpected_response",
        result?.error || "",
      );
    }
    return { name: result.name, id: result.id, mode };
  }

  async sendMagnet(magnet, mode) {
    const data = await this.request("/api/torrents/magnet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, magnet }),
    });
    return { id: data.id, mode: data.mode || mode };
  }

  async status() {
    const data = await this.bootstrap();
    return {
      reachable: true,
      proxyAddress: data.proxy_address || null,
      setupRequired: !!data.setup_required,
    };
  }
}
