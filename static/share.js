// 只读分享页的脚本。token 从地址 /分享/{token} 里取，内容全部用 textContent 渲染，
// 不拼 HTML，避免资料标题/文件名带标签时出问题。

const shareMessage = document.querySelector("#share-message");
const shareCourseName = document.querySelector("#share-course-name");
const shareMeta = document.querySelector("#share-meta");
const shareFileList = document.querySelector("#share-file-list");

function shareToken() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function formatFileSize(size) {
  if (size < 1024) return `${size} 字节`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} 千字节`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} 兆字节`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} 吉字节`;
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(`${value.replace(" ", "T")}Z`);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", { hour12: false });
}

function renderShareFiles(files) {
  shareFileList.innerHTML = "";
  if (!files.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "这门课暂时没有可下载的资料。";
    shareFileList.append(empty);
    return;
  }
  files.forEach((file) => {
    const item = document.createElement("li");
    item.className = "file-row";

    const details = document.createElement("div");
    details.className = "file-details";
    const title = document.createElement("h3");
    title.textContent = file.title;
    const meta = document.createElement("p");
    meta.className = "file-meta";
    const time = formatDateTime(file.upload_time) || "上传时间未知";
    meta.textContent = `${file.original_name} · ${formatFileSize(file.size)} · ${time}`;
    details.append(title, meta);

    const actions = document.createElement("div");
    actions.className = "file-actions";
    const download = document.createElement("a");
    download.className = "download-link";
    download.href = `/api/files/${encodeURIComponent(file.id)}/download`;
    download.textContent = "下载";
    download.setAttribute("download", "");
    actions.append(download);

    item.append(details, actions);
    shareFileList.append(item);
  });
}

async function loadShare() {
  try {
    const response = await fetch(`/api/shares/${encodeURIComponent(shareToken())}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error((data.error && data.error.message) || "分享链接不可用。");
    }
    shareCourseName.textContent = data.course.name;
    const parts = [];
    if (data.course.college) parts.push(data.course.college);
    if (data.note) parts.push(data.note);
    parts.push(`有效期至 ${formatDateTime(data.expires_at) || data.expires_at}`);
    shareMeta.textContent = parts.join(" · ");
    renderShareFiles(data.files || []);
  } catch (error) {
    shareCourseName.textContent = "分享链接不可用";
    shareMessage.textContent = error.message || "分享链接不可用。";
    shareMessage.className = "form-message error-message";
    shareFileList.innerHTML = "";
  }
}

loadShare();
