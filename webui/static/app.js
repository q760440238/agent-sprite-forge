const $ = (id) => document.getElementById(id);
const BASE_PATH = window.location.pathname.replace(/\/+$/, "");
const appUrl = (path) => `${BASE_PATH}${path}`;
let OPTIONS = { targets: [], npc_roles: [], frames: [], styles: [] };
let activeKind = $("kind").value;

function escapeHtml(text) {
  return String(text).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[char]);
}

function selectedTarget() {
  return OPTIONS.targets.find((target) => target.id === $("target").value) || OPTIONS.targets[0];
}

function selectedMode() {
  return selectedTarget()?.modes.find((mode) => mode.id === $("mode").value) || selectedTarget()?.modes[0];
}

function fillTargets() {
  $("target").innerHTML = OPTIONS.targets
    .map((target) => `<option value="${escapeHtml(target.id)}">${escapeHtml(target.label)}</option>`)
    .join("");
}

function fillModes() {
  const target = selectedTarget();
  $("mode").innerHTML = (target?.modes || [])
    .map((mode) => `<option value="${escapeHtml(mode.id)}">${escapeHtml(mode.label)}</option>`)
    .join("");
}

function fillNpcRoles() {
  $("npcRole").innerHTML = OPTIONS.npc_roles
    .map((role) => `<option value="${escapeHtml(role.id)}">${escapeHtml(role.label)}</option>`)
    .join("");
}

function fillStyles() {
  const defaultStyle = OPTIONS.styles.find(s => s.id === (OPTIONS.default_style || "retro_16bit"));
  if (defaultStyle) {
    $("style").value = defaultStyle.id;
    $("styleLabel").textContent = defaultStyle.label;
  }
}

function renderStyleModal() {
  const grouped = {};
  OPTIONS.styles.forEach((style) => {
    if (!grouped[style.group]) grouped[style.group] = [];
    grouped[style.group].push(style);
  });

  let modalHTML = '<div class="style-groups">';
  for (const [group, styles] of Object.entries(grouped)) {
    modalHTML += `<div class="style-group">
      <h4 class="style-group-title">${escapeHtml(group)}</h4>
      <div class="style-grid">`;
    styles.forEach((style) => {
      const previewUrl = `/static/style_previews/${style.id}.webp`;
      modalHTML += `<button type="button" class="style-card" data-style-id="${escapeHtml(style.id)}" data-style-label="${escapeHtml(style.label)}">
        <img class="style-card-preview" src="${previewUrl}" alt="${escapeHtml(style.label)}">
        <div class="style-card-label">${escapeHtml(style.label)}</div>
      </button>`;
    });
    modalHTML += '</div></div>';
  }
  modalHTML += '</div>';
  
  $("styleModalBody").innerHTML = modalHTML;
  
  const currentStyleId = $("style").value;
  const card = document.querySelector(`.style-card[data-style-id="${currentStyleId}"]`);
  if (card) card.classList.add("selected");
}

function syncFrameOptions() {
  const mode = selectedMode();
  const forcedCount = mode?.fixed_frame_count;
  const previousCount = Number($("frameCount").value);
  const candidateFrames = forcedCount
    ? OPTIONS.frames.filter((frame) => frame.count === forcedCount)
    : OPTIONS.frames.filter((frame) => frame.count > 1);
  const preferredCount = candidateFrames.some((frame) => frame.count === previousCount)
    ? previousCount
    : (forcedCount || mode?.default_frame_count || candidateFrames[0]?.count);

  $("frameCount").innerHTML = candidateFrames
    .map((frame) => `<option value="${frame.count}">${escapeHtml(frame.label)}</option>`)
    .join("");
  $("frameCount").value = String(preferredCount || "");
  $("frameCount").disabled = Boolean(forcedCount);
  syncFrameGrid();
}

function syncFrameGrid() {
  const frame = OPTIONS.frames.find((item) => item.count === Number($("frameCount").value));
  $("frameGrid").textContent = frame ? `${frame.rows} × ${frame.cols} 网格` : "";
}

function clearReferences() {
  $("refs").value = "";
  $("fileList").textContent = "";
}

function setControlsDisabled(container, disabled) {
  container.querySelectorAll("select, input, textarea, button").forEach((control) => {
    control.disabled = disabled;
  });
}

function syncOutputLabels(kind) {
  const isMap = kind === "map";
  $("outputSummary").textContent = isMap ? "完整场景，独立于角色素材" : "透明背景，已完成后处理";
  $("rawTitle").textContent = isMap ? "场景原图" : "原始图（模型直出透明底）";
  $("outputTitle").textContent = isMap ? "场景交付文件" : "后处理产物（透明背景）";
}

function syncAssetControls({ kindChanged = false } = {}) {
  const isSprite = $("kind").value === "sprite";
  if (kindChanged) clearReferences();
  $("spriteOpts").hidden = !isSprite;
  $("frameOpts").hidden = !isSprite;
  setControlsDisabled($("spriteOpts"), !isSprite);
  setControlsDisabled($("frameOpts"), !isSprite);
  const isNpc = isSprite && $("target").value === "npc";
  $("npcRoleWrap").hidden = !isNpc;
  $("npcRole").disabled = !isNpc;
  if (isSprite) syncFrameOptions();
  syncOutputLabels($("kind").value);
}

async function initOptions() {
  const response = await fetch(appUrl("/api/options"));
  if (!response.ok) throw new Error(`配置加载失败（HTTP ${response.status}）`);
  OPTIONS = await response.json();
  fillTargets();
  fillModes();
  fillNpcRoles();
  fillStyles();
  syncAssetControls();
}

function addUserMessage(text) {
  const conversation = $("conversation");
  conversation.insertAdjacentHTML("beforeend", `<div class="message user"><div class="avatar">你</div><div><span class="speaker">你</span><div class="bubble">${escapeHtml(text)}</div></div></div>`);
  conversation.scrollTop = conversation.scrollHeight;
}

function addAgentMessage(text) {
  const conversation = $("conversation");
  conversation.insertAdjacentHTML("beforeend", `<div class="message agent"><div class="avatar">✦</div><div><span class="speaker">Sprite Forge</span><div class="bubble">${escapeHtml(text)}</div></div></div>`);
  conversation.scrollTop = conversation.scrollHeight;
}

function formatTime(value) {
  return new Date(value).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function isAnimation(url) {
  return /\.(webp|gif)$/i.test(url);
}

function isImage(url) {
  return /\.(png|webp|gif)$/i.test(url);
}

function assetFigure(url, className = "") {
  const name = url.split("/").pop();
  return `<figure class="${className}"><img src="${appUrl(url)}" alt="${escapeHtml(name)}">
    <figcaption><a href="${appUrl(url)}" download>${escapeHtml(name)}</a></figcaption></figure>`;
}

function renderOutput(files, bundleUrl = "") {
  const animations = files.filter(isAnimation);
  const stills = files.filter((url) => isImage(url) && !isAnimation(url));
  const download = $("downloadAll");
  download.hidden = !bundleUrl;
  if (bundleUrl) download.href = appUrl(bundleUrl);

  $("animationWrap").hidden = animations.length === 0;
  $("animationPreview").innerHTML = animations.map((url) => assetFigure(url, "animation-card")).join("");
  $("framesWrap").hidden = stills.length === 0;
  $("gallery").innerHTML = stills.map((url) => assetFigure(url)).join("");
}

function finishCompleted(snapshot) {
  syncOutputLabels(snapshot.kind);
  if (Object.prototype.hasOwnProperty.call(snapshot, "raw_url")) {
    $("rawWrap").hidden = !snapshot.raw_url;
    if (snapshot.raw_url) $("raw").src = appUrl(snapshot.raw_url);
  }
  $("outWrap").hidden = false;
  renderOutput(snapshot.files || [], snapshot.bundle_url || "");
  $("go").disabled = false;
  addAgentMessage(snapshot.kind === "map"
    ? "场景素材已生成完成，下载包包含原图、提示词和交付说明。"
    : "素材已经生成完成。WebP 动画和透明 PNG 图片集已加入画廊，并已打包为 ZIP。");
  loadHistory();
}

function finishFailed(snapshot) {
  const message = snapshot.error || "任务失败，未返回具体原因。";
  log(message, true);
  addAgentMessage(`这次生成没有完成：${message}`);
  $("go").disabled = false;
  loadHistory();
}

function applyJobSnapshot(snapshot) {
  if (snapshot.prompt) {
    $("promptBox").hidden = false;
    $("prompt").textContent = snapshot.prompt;
  }
  if (snapshot.raw_url) {
    $("rawWrap").hidden = false;
    $("raw").src = appUrl(snapshot.raw_url);
  }
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function pollJob(job) {
  let notified = false;
  while (true) {
    try {
      const response = await fetch(appUrl(`/api/jobs/${encodeURIComponent(job)}`), { cache: "no-store" });
      if (response.status === 404) {
        finishFailed({ error: "任务记录已不存在，无法恢复本次生成状态。" });
        return;
      }
      if (!response.ok) throw new Error(await responseError(response));
      const snapshot = await response.json();
      applyJobSnapshot(snapshot);
      if (snapshot.status === "completed") {
        finishCompleted(snapshot);
        return;
      }
      if (snapshot.status === "failed") {
        finishFailed(snapshot);
        return;
      }
      if (!notified) {
        log("生成连接已中断，正在从任务状态恢复…", true);
        notified = true;
      }
    } catch (error) {
      if (!notified) {
        log(`恢复任务状态失败：${error.message || "网络错误"}，将继续重试。`, true);
        notified = true;
      }
    }
    await wait(3000);
  }
}

function renderHistory(items) {
  const history = $("history");
  if (!items.length) {
    history.innerHTML = '<div class="history-empty">还没有生成记录，完成第一次创作后会显示在这里。</div>';
    return;
  }
  history.innerHTML = items.map((item) => {
    const title = item.brief || "未命名素材";
    const status = item.status === "completed" ? "已完成" : item.status === "failed" ? "失败" : "处理中";
    const preview = item.files.find(isImage);
    const frameMeta = item.kind === "sprite" && item.frame_count ? ` · ${item.frame_count} 帧` : "";
    const links = [
      preview ? `<a href="${appUrl(preview)}" target="_blank" rel="noreferrer">预览</a>` : "",
      item.bundle_url ? `<a href="${appUrl(item.bundle_url)}" download>下载全部</a>` : "",
    ].join("");
    return `<div class="history-item">
      <div class="history-main"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(item.style || "默认画风")} · ${escapeHtml(item.target)}/${escapeHtml(item.mode)}${frameMeta}</span></div>
      <div class="history-meta">${formatTime(item.created_at)}<br>${escapeHtml(item.size)} · ${item.reference_count} 张参考图</div>
      <div class="history-links"><span class="history-status ${item.status === "failed" ? "failed" : ""}">${status}</span>${links}</div>
    </div>`;
  }).join("");
}

async function loadHistory() {
  try {
    const response = await fetch(appUrl("/api/history"));
    if (!response.ok) throw new Error("历史记录暂时无法加载。");
    const data = await response.json();
    renderHistory(data.items || []);
  } catch {
    $("history").innerHTML = '<div class="history-empty">历史记录暂时无法加载。</div>';
  }
}

function log(text, isError = false) {
  const el = $("log");
  if (el.textContent === "等待你的需求…") el.textContent = "";
  el.textContent += `${isError ? "[错误] " : ""}${text}\n`;
  el.scrollTop = el.scrollHeight;
}

async function responseError(response) {
  const payload = await response.json().catch(() => null);
  if (typeof payload?.detail === "string") return payload.detail;
  return `发送失败（HTTP ${response.status}）`;
}

$("kind").onchange = () => {
  const nextKind = $("kind").value;
  const kindChanged = nextKind !== activeKind;
  activeKind = nextKind;
  syncAssetControls({ kindChanged });
};
$("target").onchange = () => {
  fillModes();
  syncAssetControls();
};
$("mode").onchange = syncAssetControls;
$("frameCount").onchange = syncFrameGrid;

$("refs").onchange = () => {
  const files = [...$("refs").files];
  $("fileList").textContent = files.length ? `${files.length} 张参考图已就绪` : "";
};

$("dropZone").ondragover = (event) => {
  event.preventDefault();
  $("dropZone").classList.add("drag");
};
$("dropZone").ondragleave = () => $("dropZone").classList.remove("drag");
$("dropZone").ondrop = (event) => {
  event.preventDefault();
  $("dropZone").classList.remove("drag");
  if (event.dataTransfer.files.length) {
    $("refs").files = event.dataTransfer.files;
    $("refs").dispatchEvent(new Event("change"));
  }
};

$("go").onclick = async () => {
  const brief = $("brief").value.trim();
  if (!brief) {
    alert("请先填写需求描述");
    return;
  }
  $("go").disabled = true;
  $("log").textContent = "";
  $("rawWrap").hidden = true;
  $("outWrap").hidden = true;
  $("animationWrap").hidden = true;
  $("framesWrap").hidden = true;
  $("downloadAll").hidden = true;
  $("promptBox").hidden = true;
  $("gallery").innerHTML = "";
  addUserMessage(brief);

  const fd = new FormData();
  const kind = $("kind").value;
  fd.append("kind", kind);
  fd.append("brief", brief);
  fd.append("style", $("style").value);
  fd.append("style_note", $("styleNote").value.trim());
  fd.append("size", $("size").value);
  
  if (kind === "sprite") {
    fd.append("target", $("target").value);
    fd.append("mode", $("mode").value);
    fd.append("frame_count", $("frameCount").value);
    if ($("target").value === "npc") fd.append("role", $("npcRole").value);
  }
  
  // 添加自定义画风参考图（如果有）
  customStyleFiles.forEach(file => {
    fd.append("references", file);
  });
  // 添加其他参考图
  for (const file of $("refs").files) fd.append("references", file);

  let job;
  try {
    const response = await fetch(appUrl("/api/generate"), { method: "POST", body: fd });
    if (!response.ok) throw new Error(await responseError(response));
    const payload = await response.json();
    ({ job } = payload);
    if (payload.size && payload.requested_size && payload.size !== payload.requested_size) {
      log(`为保证 ${$("frameCount").value} 帧细节，画幅已自动提升至 ${payload.size}。`);
    }
  } catch (error) {
    const message = error.message || "发送失败";
    log(message, true);
    addAgentMessage(`需求没有发送成功：${message}`);
    $("go").disabled = false;
    return;
  }
  $("brief").value = "";
  const es = new EventSource(appUrl(`/api/stream/${job}`));
  let finished = false;
  let recovering = false;

  es.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "log") log(data.text);
    else if (data.type === "prompt") {
      $("promptBox").hidden = false;
      $("prompt").textContent = data.text;
    } else if (data.type === "raw") {
      $("rawWrap").hidden = false;
      $("raw").src = appUrl(data.url);
    } else if (data.type === "done") {
      finished = true;
      es.close();
      finishCompleted({
        kind: data.kind,
        files: data.files || [],
        bundle_url: data.bundle || "",
      });
    } else if (data.type === "error") {
      finished = true;
      es.close();
      finishFailed({ error: data.text });
    }
  };
  es.onerror = () => {
    es.close();
    if (!finished && !recovering) {
      recovering = true;
      pollJob(job).catch((error) => {
        log(`任务恢复中断：${error.message || "未知错误"}`, true);
        $("go").disabled = false;
      });
    }
  };
};

$("refreshHistory").onclick = loadHistory;

$("styleButton").onclick = () => {
  if ($("styleModalBody").children.length === 0) {
    renderStyleModal();
  }
  renderCustomStyleGallery();
  $("styleModal").classList.add("open");
};

$("styleModalClose").onclick = () => {
  $("styleModal").classList.remove("open");
};

$("styleModal").onclick = (e) => {
  if (e.target === $("styleModal")) {
    $("styleModal").classList.remove("open");
  }
};

// 自定义画风管理（LocalStorage持久化）
const CUSTOM_STYLES_KEY = "sprite_forge_custom_styles";
let customStyles = [];
let pendingCustomStyleFile = null;
let selectedCustomStyleId = null;

// 从LocalStorage加载自定义画风
function loadCustomStyles() {
  try {
    const stored = localStorage.getItem(CUSTOM_STYLES_KEY);
    customStyles = stored ? JSON.parse(stored) : [];
  } catch (error) {
    console.error("加载自定义画风失败:", error);
    customStyles = [];
  }
}

// 保存自定义画风到LocalStorage
function saveCustomStyles() {
  try {
    localStorage.setItem(CUSTOM_STYLES_KEY, JSON.stringify(customStyles));
  } catch (error) {
    console.error("保存自定义画风失败:", error);
    alert("保存失败：存储空间可能已满");
  }
}

// 生成下一个默认名称
function getNextCustomStyleName() {
  const existingNumbers = customStyles
    .map(s => s.name)
    .filter(name => /^自定义\d+$/.test(name))
    .map(name => parseInt(name.replace("自定义", "")));
  
  const maxNumber = existingNumbers.length > 0 ? Math.max(...existingNumbers) : 0;
  return `自定义${maxNumber + 1}`;
}

// 渲染自定义画风画廊
function renderCustomStyleGallery() {
  const gallery = $("customStyleGallery");
  const addButton = `
    <button type="button" id="addCustomStyleBtn" class="custom-style-add-card">
      <span class="add-icon">+</span>
      <span class="add-text">添加画风</span>
    </button>
  `;
  
  const cards = customStyles.map((style) => {
    const isSelected = style.id === selectedCustomStyleId;
    return `
      <div class="custom-style-card ${isSelected ? 'selected' : ''}" data-custom-id="${escapeHtml(style.id)}">
        <img class="custom-style-card-preview" src="${escapeHtml(style.imageData)}" alt="${escapeHtml(style.name)}">
        <div class="custom-style-card-label">${escapeHtml(style.name)}</div>
        <button type="button" class="remove-btn" data-custom-id="${escapeHtml(style.id)}">×</button>
      </div>
    `;
  }).join("");
  
  gallery.innerHTML = addButton + cards;
  
  // 绑定添加按钮事件
  const addBtn = gallery.querySelector("#addCustomStyleBtn");
  if (addBtn) {
    addBtn.onclick = () => {
      $("customStyleUpload").click();
    };
  }
  
  // 绑定删除按钮事件
  gallery.querySelectorAll(".remove-btn").forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const customId = btn.dataset.customId;
      if (confirm("确定要删除这个自定义画风吗？")) {
        customStyles = customStyles.filter(s => s.id !== customId);
        if (selectedCustomStyleId === customId) {
          selectedCustomStyleId = null;
        }
        saveCustomStyles();
        renderCustomStyleGallery();
      }
    };
  });
  
  // 绑定卡片选择事件
  gallery.querySelectorAll(".custom-style-card").forEach(card => {
    card.onclick = () => {
      const customId = card.dataset.customId;
      const style = customStyles.find(s => s.id === customId);
      if (!style) return;
      
      // 清除内置画风选择
      document.querySelectorAll("#styleModalBody .style-card").forEach(c => c.classList.remove("selected"));
      $("style").value = "";
      
      // 选择自定义画风
      selectedCustomStyleId = customId;
      $("styleLabel").textContent = style.name;
      renderCustomStyleGallery();
      $("styleModal").classList.remove("open");
    };
  });
}

// 文件上传处理
$("customStyleUpload").onchange = (e) => {
  const file = e.target.files[0];
  if (!file) return;
  
  // 验证文件类型
  if (!file.type.startsWith("image/")) {
    alert("请选择图片文件");
    e.target.value = "";
    return;
  }
  
  // 验证文件大小（限制5MB）
  if (file.size > 5 * 1024 * 1024) {
    alert("图片大小不能超过5MB");
    e.target.value = "";
    return;
  }
  
  pendingCustomStyleFile = file;
  
  // 打开命名弹窗
  const defaultName = getNextCustomStyleName();
  $("customStyleNameInput").value = defaultName;
  $("nameCustomStyleModal").classList.add("open");
  
  // 聚焦输入框并选中文本
  setTimeout(() => {
    $("customStyleNameInput").focus();
    $("customStyleNameInput").select();
  }, 100);
  
  e.target.value = "";
};

// 确认添加自定义画风
$("confirmCustomStyleName").onclick = () => {
  const name = $("customStyleNameInput").value.trim();
  if (!name) {
    alert("请输入画风名称");
    return;
  }
  
  if (!pendingCustomStyleFile) {
    $("nameCustomStyleModal").classList.remove("open");
    return;
  }
  
  const reader = new FileReader();
  reader.onload = (event) => {
    const newStyle = {
      id: `custom_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      name: name,
      imageData: event.target.result,
      createdAt: new Date().toISOString()
    };
    
    customStyles.push(newStyle);
    saveCustomStyles();
    renderCustomStyleGallery();
    
    $("nameCustomStyleModal").classList.remove("open");
    pendingCustomStyleFile = null;
  };
  
  reader.onerror = () => {
    alert("读取图片失败，请重试");
    $("nameCustomStyleModal").classList.remove("open");
    pendingCustomStyleFile = null;
  };
  
  reader.readAsDataURL(pendingCustomStyleFile);
};

// 取消添加自定义画风
$("cancelCustomStyleName").onclick = () => {
  $("nameCustomStyleModal").classList.remove("open");
  pendingCustomStyleFile = null;
};

// 命名弹窗回车确认
$("customStyleNameInput").onkeypress = (e) => {
  if (e.key === "Enter") {
    $("confirmCustomStyleName").click();
  }
};

// 点击弹窗背景关闭
$("nameCustomStyleModal").onclick = (e) => {
  if (e.target === $("nameCustomStyleModal")) {
    $("cancelCustomStyleName").click();
  }
};

$("styleModalBody").onclick = (e) => {
  const card = e.target.closest(".style-card");
  if (!card) return;
  
  // 清除自定义画风选择
  selectedCustomStyleId = null;
  renderCustomStyleGallery();
  
  document.querySelectorAll(".style-card").forEach((c) => c.classList.remove("selected"));
  card.classList.add("selected");
  
  const styleId = card.dataset.styleId;
  const styleLabel = card.dataset.styleLabel;
  $("style").value = styleId;
  $("styleLabel").textContent = styleLabel;
  $("styleModal").classList.remove("open");
};

// 初始化
loadCustomStyles();
renderCustomStyleGallery();

initOptions().catch((error) => {
  log(error.message || "配置加载失败", true);
  $("go").disabled = true;
});
loadHistory();
