/*
 * Livechat AI Widget - X-SHA ERPNext
 * Di-load global lewat hooks.py -> app_include_js
 * Floating bubble pojok kanan bawah, muncul di semua halaman desk.
 * Config (enabled, ai_name, welcome message, passcode gate) diambil dari
 * server tiap load halaman.
 */
(function () {
	if (frappe.session.user === "Guest") return;

	if (!document.getElementById("xsha-livechat-style")) {
		const style = document.createElement("style");
		style.id = "xsha-livechat-style";
		style.textContent = `
			@keyframes xshaTypingBlink { 0%, 80%, 100% { opacity: 0.2; } 40% { opacity: 1; } }
			.xsha-typing-dot {
				display: inline-block; width: 6px; height: 6px; margin: 0 2px;
				background: currentColor; border-radius: 50%;
				animation: xshaTypingBlink 1.4s infinite both;
			}
			.xsha-typing-dot:nth-child(2) { animation-delay: 0.2s; }
			.xsha-typing-dot:nth-child(3) { animation-delay: 0.4s; }
		`;
		document.head.appendChild(style);
	}

	frappe.call({
		method: "custom_reports.api.livechat.get_widget_config",
		callback: function (r) {
			const config = r.message || {};
			if (config.enabled) {
				initWidget(config);
			}
		},
	});

	function initWidget(config) {
		const aiName = config.ai_name || "X-SHA Livechat AI";
		const STORAGE_KEY = "xsha_livechat_history_" + frappe.session.user;

		function loadHistory() {
			try {
				return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
			} catch (e) {
				return [];
			}
		}

		function saveHistory(history) {
			try {
				sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history));
			} catch (e) {}
		}

		let history = loadHistory();
		let sending = false;
		let typingEl = null;

		const bubble = document.createElement("div");
		bubble.id = "xsha-livechat-bubble";
		bubble.innerHTML = "💬";
		bubble.style.cssText = `
			position: fixed; bottom: 24px; right: 24px; width: 56px; height: 56px;
			border-radius: 50%; background: #2490ef; color: #fff; font-size: 26px;
			display: flex; align-items: center; justify-content: center;
			cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,0.25); z-index: 9999;
			user-select: none;
		`;
		document.body.appendChild(bubble);

		const panel = document.createElement("div");
		panel.id = "xsha-livechat-panel";
		panel.style.cssText = `
			position: fixed; bottom: 92px; right: 24px; width: 360px; height: 480px;
			background: var(--fg-color, #fff); border-radius: 10px; box-shadow: 0 6px 24px rgba(0,0,0,0.3);
			display: none; flex-direction: column; z-index: 9999; overflow: hidden;
			border: 1px solid var(--border-color, #d1d8dd); font-family: inherit;
		`;
		panel.innerHTML = `
			<div style="padding:10px 14px;background:#2490ef;color:#fff;font-weight:600;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;">
				<span>${frappe.utils.escape_html(aiName)}</span>
				<span id="xsha-livechat-close" style="cursor:pointer;font-size:18px;">&times;</span>
			</div>
			<div id="xsha-livechat-body" style="flex:1;display:flex;flex-direction:column;overflow:hidden;"></div>
		`;
		document.body.appendChild(panel);

		const bodyEl = panel.querySelector("#xsha-livechat-body");

		bubble.addEventListener("click", () => {
			panel.style.display = panel.style.display === "none" ? "flex" : "none";
			const input = panel.querySelector("#xsha-livechat-input, #xsha-livechat-passcode");
			if (panel.style.display === "flex" && input) input.focus();
		});
		panel.querySelector("#xsha-livechat-close").addEventListener("click", () => {
			panel.style.display = "none";
		});

		if (config.passcode_required) {
			renderLockScreen();
		} else {
			renderChatUI();
		}

		function renderLockScreen() {
			bodyEl.innerHTML = `
				<div style="padding:20px;text-align:center;">
					<p style="margin-bottom:10px;font-size:13px;">Masukkan passcode buat mulai chat:</p>
					<input id="xsha-livechat-passcode" type="password"
						style="width:100%;box-sizing:border-box;padding:6px 8px;border:1px solid var(--border-color,#d1d8dd);border-radius:6px;margin-bottom:8px;font-size:13px;" />
					<button id="xsha-livechat-unlock-btn" class="btn btn-primary btn-sm" style="width:100%;">Buka</button>
					<div id="xsha-livechat-unlock-error" style="color:#e24c4c;font-size:12px;margin-top:8px;"></div>
				</div>
			`;
			const pcInput = bodyEl.querySelector("#xsha-livechat-passcode");
			const unlockBtn = bodyEl.querySelector("#xsha-livechat-unlock-btn");
			const errEl = bodyEl.querySelector("#xsha-livechat-unlock-error");

			function tryUnlock() {
				const val = pcInput.value.trim();
				if (!val) return;
				unlockBtn.disabled = true;
				frappe.call({
					method: "custom_reports.api.livechat.unlock",
					args: { passcode: val },
					callback: function (r) {
						unlockBtn.disabled = false;
						if (r.message && r.message.ok) {
							renderChatUI();
						} else {
							errEl.textContent = "Passcode salah, coba lagi.";
							pcInput.value = "";
							pcInput.focus();
						}
					},
					error: function () {
						unlockBtn.disabled = false;
						errEl.textContent = "Gagal verifikasi, coba lagi.";
					},
				});
			}

			unlockBtn.addEventListener("click", tryUnlock);
			pcInput.addEventListener("keydown", (e) => {
				if (e.key === "Enter") tryUnlock();
			});
			setTimeout(() => pcInput.focus(), 50);
		}

		function renderChatUI() {
			bodyEl.innerHTML = `
				<div id="xsha-livechat-messages" style="flex:1;overflow-y:auto;padding:10px;font-size:13px;"></div>
				<div style="padding:8px;border-top:1px solid var(--border-color,#d1d8dd);display:flex;gap:6px;flex-shrink:0;">
					<textarea id="xsha-livechat-input" rows="1" placeholder="Tanya sesuatu..."
						style="flex:1;resize:none;border:1px solid var(--border-color,#d1d8dd);border-radius:6px;padding:6px 8px;font-size:13px;"></textarea>
					<button id="xsha-livechat-send" class="btn btn-primary btn-sm">Kirim</button>
				</div>
			`;

			const messagesEl = bodyEl.querySelector("#xsha-livechat-messages");
			const inputEl = bodyEl.querySelector("#xsha-livechat-input");
			const sendBtn = bodyEl.querySelector("#xsha-livechat-send");

			function renderMessage(role, content) {
				const div = document.createElement("div");
				const isUser = role === "user";
				div.style.cssText = `
					margin-bottom:8px; padding:7px 10px; border-radius:8px; max-width:85%;
					white-space:pre-wrap; word-break:break-word;
					${isUser ? "background:#2490ef;color:#fff;margin-left:auto;" : "background:var(--control-bg,#f4f5f6);color:var(--text-color,#1f272e);"}
				`;
				div.textContent = content;
				messagesEl.appendChild(div);
				messagesEl.scrollTop = messagesEl.scrollHeight;
			}

			function showTyping() {
				typingEl = document.createElement("div");
				typingEl.style.cssText = `
					margin-bottom:8px; padding:9px 12px; border-radius:8px; width:fit-content;
					background:var(--control-bg,#f4f5f6); color:var(--text-color,#1f272e);
				`;
				typingEl.innerHTML = `<span class="xsha-typing-dot"></span><span class="xsha-typing-dot"></span><span class="xsha-typing-dot"></span>`;
				messagesEl.appendChild(typingEl);
				messagesEl.scrollTop = messagesEl.scrollHeight;
			}

			function hideTyping() {
				if (typingEl) {
					typingEl.remove();
					typingEl = null;
				}
			}

			function renderAll() {
				messagesEl.innerHTML = "";
				history.forEach((m) => {
					if (m.role === "user" || m.role === "assistant") {
						if (m.content) renderMessage(m.role, m.content);
					}
				});
				if (history.length === 0) {
					renderMessage("assistant", config.welcome_message || "Halo! Ada yang bisa dibantu?");
				}
			}

			renderAll();
			inputEl.focus();

			function send() {
				const text = inputEl.value.trim();
				if (!text || sending) return;
				sending = true;
				sendBtn.disabled = true;
				inputEl.value = "";
				renderMessage("user", text);
				showTyping();

				frappe.call({
					method: "custom_reports.api.livechat_opencode.chat",
					args: { message: text, history: JSON.stringify(history) },
					callback: function (r) {
						sending = false;
						sendBtn.disabled = false;
						hideTyping();
						if (r.message) {
							history = r.message.history || history;
							renderMessage("assistant", r.message.reply || "(tidak ada jawaban)");
							saveHistory(history);
						}
					},
					error: function () {
						sending = false;
						sendBtn.disabled = false;
						hideTyping();
						renderMessage("assistant", "Waduh, ada error. Coba lagi atau cek dengan IT.");
					},
				});
			}

			sendBtn.addEventListener("click", send);
			inputEl.addEventListener("keydown", (e) => {
				if (e.key === "Enter" && !e.shiftKey) {
					e.preventDefault();
					send();
				}
			});
		}
	}
})();
