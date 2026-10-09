async function loadCourseFiles(courseId, page = 1) {
  currentFilePage = page;
  showState(fileList, "正在加载资料...");
  filePagination.innerHTML = "";
  try {
    const response = await fetch(`/api/courses/${encodeURIComponent(courseId)}/files?page=${page}&page_size=12`);
    if (!response.ok) {
      if (response.status === 404) throw new Error("课程不存在");
      throw new Error("资料加载失败");
    }
    renderFiles(await response.json(), courseId);
  } catch (error) {
    showState(fileList, `${error.message}，请返回课程列表重试。`, true);
    fileCount.textContent = "";
  }
}

function syncFileSelection() {
  const count = selectedFileIds.size;
  if (fileSelectionCount) fileSelectionCount.textContent = count ? `已选 ${count} 份` : "";
  if (archiveSelectedButton) archiveSelectedButton.disabled = count === 0;
  // 批量审核只有管理员能用，普通访客连按钮都不显示。
  const isAdmin = currentUser?.role === "admin";
  [batchApproveButton, batchRejectButton].forEach((button) => {
    if (!button) return;
    button.hidden = !isAdmin;
    button.disabled = count === 0;
  });
  if (fileSelectAll) {
    const onPage = currentFileIds.filter((id) => selectedFileIds.has(id)).length;
    fileSelectAll.checked = currentFileIds.length > 0 && onPage === currentFileIds.length;
    // 只选了一部分时用「半选」状态，避免看起来像全选或全不选。
    fileSelectAll.indeterminate = onPage > 0 && onPage < currentFileIds.length;
  }
}

function archiveUrl(ids) {
  const params = new URLSearchParams();
  ids.forEach((id) => params.append("资料编号", String(id)));
  const query = params.toString();
  const base = `/api/courses/${encodeURIComponent(currentCourseId)}/archive`;
  return query ? `${base}?${query}` : base;
}

function downloadArchive(ids) {
  // 用原生导航触发下载，浏览器边收边写盘；若改用 fetch + blob，大课程会把整个
  // 压缩包堆进页面内存。
  const link = document.createElement("a");
  link.href = archiveUrl(ids);
  link.setAttribute("download", "");
  document.body.append(link);
  link.click();
  link.remove();
}

function setExportMessage(message, isError = false) {
  if (!exportMessage) return;
  exportMessage.textContent = message;
  exportMessage.className = isError ? "form-message error-message" : "form-message";
}

// CSV 导出走 fetch + blob，而不是像打包下载那样直接导航：导出会失败
// （比如结果超过行数上限），失败时接口返回的是 JSON，直接导航会让浏览器把
// 一坨 JSON 显示出来。CSV 有行数上限，体积可控，堆进内存没问题。
async function saveCsv(response, filename) {
  if (!response.ok) throw new Error(await readError(response, "导出失败。"));
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
  setExportMessage("已开始下载。");
}

async function exportCourseFiles() {
  if (!currentCourseId) return;
  setExportMessage("正在导出...");
  try {
    const response = await fetch(
      `/api/courses/${encodeURIComponent(currentCourseId)}/files/export`
    );
    const course = currentCourse?.name || "课程";
    await saveCsv(response, `${course}-资料清单.csv`);
  } catch (error) {
    setExportMessage(error.message || "导出失败。", true);
  }
}

async function exportAuditLogs() {
  setExportMessage("正在导出...");
  try {
    // 用与列表完全相同的筛选条件，否则「列表 30 条、导出 12 条」会让人怀疑数据。
    const response = await fetch(`/api/audit/export?${auditFilterParams()}`);
    await saveCsv(response, "操作记录.csv");
  } catch (error) {
    setExportMessage(error.message || "导出失败。", true);
  }
}

function initArchiveControls() {
  if (!fileToolbar) return;
  archiveSelectedButton?.addEventListener("click", () => {
    if (selectedFileIds.size) downloadArchive([...selectedFileIds]);
  });
  archiveAllButton?.addEventListener("click", () => downloadArchive([]));
  exportFilesButton?.addEventListener("click", exportCourseFiles);
  fileSelectAll?.addEventListener("change", () => {
    // 「全选」只作用于当前这一页，已经跨页选中的资料不会被清掉。
    if (fileSelectAll.checked) currentFileIds.forEach((id) => selectedFileIds.add(id));
    else currentFileIds.forEach((id) => selectedFileIds.delete(id));
    fileList.querySelectorAll(".file-select").forEach((box, index) => {
      box.checked = selectedFileIds.has(currentFileIds[index]);
    });
    syncFileSelection();
  });
  batchApproveButton?.addEventListener("click", () => batchReviewFiles("approved"));
  batchRejectButton?.addEventListener("click", () => batchReviewFiles("rejected"));
}

async function batchReviewFiles(status) {
  const ids = [...selectedFileIds];
  if (!ids.length) return;
  const action = status === "approved" ? "通过" : "拒绝";
  if (!window.confirm(`确定${action}选中的 ${ids.length} 份资料吗？`)) return;
  const response = await fetch("/api/files/batch/review", {
    // 必须是 POST：后端把批量审核注册在 POST 上。写成 PATCH 的话，
    // /api/files/batch/review 会被 PATCH /api/files/{资料编号}/review 抢先匹配，
    // 把 "batch" 当编号解析 → 422（实测确认；中文路径同理，见 app/api/files.py 注释）。
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, status }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "批量审核失败。"));
    return;
  }
  const result = await response.json();
  selectedFileIds.clear();
  await loadCourseFiles(currentCourseId, currentFilePage);
  await refreshCourse();
  // 部分失败必须让人看见是哪几份，不能只报「完成」。
  window.alert(describeBatchResult("资料", result));
}

async function editFile(file, courseId) {
  const title = window.prompt("请输入新的资料标题", file.title);
  if (title === null) return;
  const response = await fetch(`/api/files/${encodeURIComponent(file.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, version: file.version }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "资料更新失败。"));
    return;
  }
  await loadCourseFiles(courseId, currentFilePage);
}

async function removeFile(file, courseId) {
  if (!window.confirm(`确定删除“${file.title}”吗？`)) return;
  const response = await fetch(`/api/files/${encodeURIComponent(file.id)}`, { method: "DELETE" });
  if (!response.ok) {
    window.alert(await readError(response, "资料删除失败。"));
    return;
  }
  await loadCourseFiles(courseId, currentFilePage);
}

async function reviewFile(file, courseId, status) {
  const action = status === "approved" ? "通过" : "拒绝";
  if (!window.confirm(`确定${action}“${file.title}”吗？`)) return;
  const response = await fetch(`/api/files/${encodeURIComponent(file.id)}/review`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "资料审核失败。"));
    return;
  }
  await loadCourseFiles(courseId, currentFilePage);
  await refreshCourse();
}

function renderCourseActions(course) {
  if (!courseActions) return;
  courseActions.hidden = currentUser?.role !== "admin";
  courseActions.innerHTML = "";
  if (courseActions.hidden) return;
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "text-button";
  edit.textContent = "编辑课程";
  edit.addEventListener("click", () => editCourse(course));
  const share = document.createElement("button");
  share.type = "button";
  share.className = "text-button";
  share.textContent = "分享链接";
  share.addEventListener("click", () => createShareLink(course));
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "text-button danger-button";
  remove.textContent = "删除课程";
  remove.addEventListener("click", () => removeCourse(course));
  courseActions.append(edit, share, remove);
}

async function editCourse(course) {
  const name = window.prompt("请输入新的课程名称", course.name);
  if (name === null) return;
  const response = await fetch(`/api/courses/${encodeURIComponent(course.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, version: course.version }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "课程更新失败。"));
    return;
  }
  // 编辑接口返回的是普通 Course（没有 file_count），合并而不是整体覆盖，
  // 否则课程摘要里的「N 份已通过资料」会短暂变成 undefined。
  currentCourse = { ...currentCourse, ...(await response.json()) };
  courseName.textContent = currentCourse.name;
  courseContext.textContent = courseContextText(currentCourse);
  renderCourseActions(currentCourse);
}

async function createShareLink(course) {
  const answer = window.prompt("分享链接有效期（天，1-90）", "7");
  if (answer === null) return;
  const days = Number(answer);
  if (!Number.isInteger(days) || days < 1 || days > 90) {
    window.alert("请输入 1 到 90 之间的整数。");
    return;
  }
  const response = await fetch(
    `/api/courses/${encodeURIComponent(course.id)}/share`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days }),
    }
  );
  if (!response.ok) {
    window.alert(await readError(response, "创建分享链接失败。"));
    return;
  }
  const data = await response.json();
  const url = new URL(data.url, window.location.origin).href;
  window.prompt("分享链接已创建（Ctrl+C 复制）：", url);
}

async function removeCourse(course) {
  if (!window.confirm(`确定删除“${course.name}”及其全部资料吗？`)) return;
  const response = await fetch(`/api/courses/${encodeURIComponent(course.id)}`, { method: "DELETE" });
  if (!response.ok) {
    window.alert(await readError(response, "课程删除失败。"));
    return;
  }
  window.location.href = "/";
}

function courseContextText(course) {
  const context = [course.college].filter(Boolean).join(" · ");
  return `${context ? `${context} · ` : ""}${course.file_count} 份已通过资料`;
}

async function refreshCourse() {
  if (!currentCourseId) return;
  const response = await fetch(`/api/courses/${encodeURIComponent(currentCourseId)}`);
  if (!response.ok) return;
  currentCourse = await response.json();
  courseName.textContent = currentCourse.name;
  courseContext.textContent = courseContextText(currentCourse);
  renderCourseActions(currentCourse);
}

function fileExtension(name) {
  const match = /\.([^.]+)$/.exec(name || "");
  return match ? match[1].toLowerCase() : "";
}

function isPreviewable(file) {
  const extension = fileExtension(file.original_name);
  return (
    PREVIEW_IMAGE_EXTENSIONS.has(extension) ||
    PREVIEW_DOCUMENT_EXTENSIONS.has(extension)
  );
}

function openPreview(file) {
  if (!previewDialog) return;
  const source = `/api/files/${encodeURIComponent(file.id)}/preview`;
  previewTitle.textContent = file.title;
  if (previewDownload) {
    previewDownload.href = `/api/files/${encodeURIComponent(file.id)}/download`;
  }
  previewBody.innerHTML = "";
  let element;
  if (PREVIEW_IMAGE_EXTENSIONS.has(fileExtension(file.original_name))) {
    element = document.createElement("img");
    element.src = source;
    element.alt = file.title;
  } else {
    element = document.createElement("iframe");
    element.src = source;
    element.title = file.title;
  }
  previewBody.append(element);
  previewDialog.hidden = false;
  document.body.classList.add("preview-open");
  previewClose?.focus();
}

function closePreview() {
  if (!previewDialog || previewDialog.hidden) return;
  previewDialog.hidden = true;
  // 清空内容才能真正终止 iframe 里的加载与渲染。
  previewBody.innerHTML = "";
  document.body.classList.remove("preview-open");
}

function previewButton(file) {
  if (!isPreviewable(file)) return null;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "text-button";
  button.textContent = "预览";
  button.addEventListener("click", () => openPreview(file));
  return button;
}

function fileSelectionHint() {
  return `单个文件不超过 ${formatFileSize(maxFileSize)}。`;
}

function updateFileSelection() {
  const files = Array.from(fileInput.files || []);
  if (!files.length) {
    fileSelection.textContent = fileSelectionHint();
    fileSelection.className = "form-hint";
    return;
  }
  const total = files.reduce((sum, file) => sum + file.size, 0);
  const summary = `${files.length} 个文件 · 共 ${formatFileSize(total)}`;
  const oversized = files.filter((file) => file.size > maxFileSize);
  if (oversized.length) {
    fileSelection.textContent = `${summary}；${oversized
      .map((file) => file.name)
      .join("、")} 超过 ${formatFileSize(maxFileSize)}`;
    fileSelection.className = "form-hint error-message";
    return;
  }
  fileSelection.textContent = `${summary}：${files.map((file) => file.name).join("、")}`;
  fileSelection.className = "form-hint";
}

function setUploadProgress(value, label) {
  uploadProgress.hidden = false;
  uploadProgress.value = value;
  uploadProgressLabel.hidden = false;
  uploadProgressLabel.textContent = label;
}

function resetUploadProgress() {
  uploadProgress.hidden = true;
  uploadProgress.value = 0;
  uploadProgressLabel.hidden = true;
}

function finishUpload(hideProgress = true) {
  uploadButton.disabled = false;
  uploadButton.textContent = "上传资料";
  if (hideProgress) window.setTimeout(resetUploadProgress, 800);
}

function uploadOne(courseId, file, title, onProgress) {
  return new Promise((resolve) => {
    const form = new FormData();
    form.append("title", title);
    form.append("file", file, file.name);
    const request = new XMLHttpRequest();
    request.open("POST", `/api/courses/${encodeURIComponent(courseId)}/files`);
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      onProgress(event.loaded / event.total);
    });
    request.addEventListener("load", () => {
      let body = {};
      try {
        body = JSON.parse(request.responseText);
      } catch (error) {
        body = {};
      }
      if (request.status < 200 || request.status >= 300) {
        const detail = typeof body.detail === "string" ? body.detail : null;
        resolve({ ok: false, message: body.error?.message || detail || "上传失败" });
        return;
      }
      resolve({ ok: true, file: body });
    });
    request.addEventListener("error", () => resolve({ ok: false, message: "网络异常" }));
    request.addEventListener("timeout", () => resolve({ ok: false, message: "上传超时" }));
    request.timeout = 300000;
    request.send(form);
  });
}

function setUploadMessage(text, isError = false) {
  uploadMessage.textContent = text;
  uploadMessage.className = isError ? "form-message error-message" : "form-message success-message";
}

function appendUploadResult(name, ok, detail) {
  if (!uploadResults) return;
  const item = document.createElement("li");
  item.className = ok ? "upload-result-ok" : "upload-result-fail";
  item.textContent = ok ? `✓ ${name}：${detail}` : `✕ ${name}：${detail}`;
  uploadResults.append(item);
}

function titleForFile(file, fallback) {
  const base = file.name.replace(/\.[^.]+$/, "").trim();
  return base || fallback || file.name;
}

async function uploadFiles(courseId, event) {
  event.preventDefault();
  uploadMessage.textContent = "";
  uploadMessage.className = "form-message";
  if (uploadResults) uploadResults.innerHTML = "";

  const files = Array.from(fileInput.files || []);
  const title = document.querySelector("#file-title").value.trim();
  if (!files.length) {
    setUploadMessage("请选择要上传的文件。", true);
    return;
  }
  if (files.length === 1 && !title) {
    setUploadMessage("资料标题不能为空。", true);
    return;
  }
  const oversized = files.find((file) => file.size > maxFileSize);
  if (oversized) {
    setUploadMessage(`${oversized.name} 超过 ${formatFileSize(maxFileSize)}。`, true);
    return;
  }

  uploadButton.disabled = true;
  uploadButton.textContent = "上传中...";
  setUploadProgress(0, `准备上传 ${files.length} 个文件`);

  let succeeded = 0;
  const failures = [];
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    const fileTitle = files.length === 1 ? title : titleForFile(file, title);
    const report = (fraction, suffix) => {
      const value = Math.round(((index + fraction) / files.length) * 100);
      setUploadProgress(value, `正在上传 ${index + 1}/${files.length}：${file.name}${suffix}`);
    };
    report(0, "");
    const result = await uploadOne(courseId, file, fileTitle, (fraction) => {
      report(fraction, `（${Math.round(fraction * 100)}%）`);
    });
    if (result.ok) {
      succeeded += 1;
      appendUploadResult(file.name, true, "上传成功");
    } else {
      failures.push(`${file.name}：${result.message}`);
      appendUploadResult(file.name, false, result.message);
    }
  }

  setUploadProgress(100, "上传完成");
  if (succeeded) {
    await loadCourseFiles(courseId, 1);
    await refreshCourse();
    await loadCourseQuota();
    if (currentUser) await loadMyUploads(1);
  }
  if (failures.length) {
    setUploadMessage(`${succeeded} 个成功，${failures.length} 个失败：${failures.join("；")}`, true);
  } else {
    uploadForm.reset();
    updateFileSelection();
    setUploadMessage(
      currentUser?.role === "admin"
        ? `已上传 ${succeeded} 份资料，全部发布。`
        : `已上传 ${succeeded} 份资料，正在等待管理员审核。`
    );
  }
  finishUpload(false);
}

function initDropZone() {
  if (!dropZone || !fileInput) return;
  ["dragenter", "dragover"].forEach((type) => {
    dropZone.addEventListener(type, (event) => {
      event.preventDefault();
      dropZone.classList.add("drop-zone-active");
    });
  });
  ["dragleave", "drop"].forEach((type) => {
    dropZone.addEventListener(type, (event) => {
      event.preventDefault();
      dropZone.classList.remove("drop-zone-active");
    });
  });
  dropZone.addEventListener("drop", (event) => {
    const dropped = event.dataTransfer?.files;
    if (!dropped || !dropped.length) return;
    const transfer = new DataTransfer();
    Array.from(dropped).forEach((file) => transfer.items.add(file));
    fileInput.files = transfer.files;
    updateFileSelection();
  });
}

async function createCourse(event) {
  event.preventDefault();
  courseCreateMessage.textContent = "正在创建...";
  courseCreateMessage.className = "form-message";
  const submitButton = courseCreateForm.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const response = await fetch("/api/courses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(courseCreateForm))),
    });
    if (!response.ok) throw new Error(await readError(response, "课程创建失败。"));
    courseCreateForm.reset();
    courseCreateMessage.textContent = "课程创建成功。";
    courseCreateMessage.className = "form-message success-message";
    await loadCourses(1);
  } catch (error) {
    courseCreateMessage.textContent = error.message || "课程创建失败。";
    courseCreateMessage.className = "form-message error-message";
  } finally {
    submitButton.disabled = false;
  }
}

function userQuery(page) {
  const params = new URLSearchParams({ page: String(page), page_size: "10" });
  const keyword = userFilterKeyword.value.trim();
  if (keyword) params.set("关键词", keyword);
  if (userFilterRole.value) params.set("角色", userFilterRole.value);
  return params;
}

// 资料评论：弹层里展示 + 发表 + 删除，打开期间每 4 秒轮询一次（非实时）。
function openComments(file) {
  if (!commentDialog) return;
  commentFileId = file.id;
  commentTitle.textContent = `评论 · ${file.title}`;
  commentMessage.textContent = "";
  commentMessage.className = "form-message";
  if (currentUser) {
    commentForm.hidden = false;
    commentHint.hidden = true;
  } else {
    commentForm.hidden = true;
    commentHint.hidden = false;
    commentHint.textContent = "登录后即可发表评论。";
  }
  commentList.innerHTML = "";
  commentDialog.hidden = false;
  document.body.classList.add("preview-open");
  commentClose?.focus();
  loadComments();
  startCommentPolling();
}

function closeComments() {
  if (!commentDialog || commentDialog.hidden) return;
  commentDialog.hidden = true;
  document.body.classList.remove("preview-open");
  stopCommentPolling();
  commentFileId = null;
}

function startCommentPolling() {
  stopCommentPolling();
  commentTimer = window.setInterval(() => {
    if (commentFileId != null) loadComments();
  }, 4000);
}

function stopCommentPolling() {
  if (commentTimer) {
    window.clearInterval(commentTimer);
    commentTimer = null;
  }
}

function refreshCourseFileCounts() {
  if (currentCourseId) loadCourseFiles(currentCourseId, currentFilePage);
}

async function loadComments() {
  if (!commentList || commentFileId == null) return;
  try {
    const response = await fetch(
      `/api/files/${encodeURIComponent(commentFileId)}/comments?page_size=50`
    );
    if (!response.ok) throw new Error(await readError(response, "评论加载失败。"));
    renderComments((await response.json()).items || []);
  } catch (error) {
    showState(commentList, error.message || "评论加载失败。", true);
  }
}

function renderComments(items) {
  commentList.innerHTML = "";
  if (!items.length) {
    showState(commentList, "还没有评论，来发第一条吧。");
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("li");
    row.className = "comment-row";
    const head = document.createElement("div");
    head.className = "comment-head";
    const who = document.createElement("strong");
    who.textContent = item.username;
    const when = document.createElement("span");
    when.className = "muted";
    when.textContent = formatDateTime(item.created_at) || item.created_at;
    head.append(who, when);
    if (currentUser && (currentUser.role === "admin" || currentUser.id === item.user_id)) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "text-button danger-button";
      remove.textContent = "删除";
      remove.addEventListener("click", () => deleteComment(item.id));
      head.append(remove);
    }
    const body = document.createElement("p");
    body.className = "comment-text";
    body.textContent = item.body;
    row.append(head, body);
    commentList.append(row);
  });
}

async function submitComment(event) {
  event.preventDefault();
  if (commentFileId == null) return;
  const body = commentInput.value.trim();
  if (!body) {
    commentMessage.textContent = "评论不能为空。";
    commentMessage.className = "form-message error-message";
    return;
  }
  try {
    const response = await fetch(
      `/api/files/${encodeURIComponent(commentFileId)}/comments`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      }
    );
    if (!response.ok) throw new Error(await readError(response, "发表失败。"));
    commentInput.value = "";
    commentMessage.textContent = "";
    commentMessage.className = "form-message";
    await loadComments();
    refreshCourseFileCounts();
  } catch (error) {
    commentMessage.textContent = error.message || "发表失败。";
    commentMessage.className = "form-message error-message";
  }
}

async function deleteComment(commentId) {
  if (!window.confirm("确定删除这条评论吗？")) return;
  const response = await fetch(`/api/comments/${encodeURIComponent(commentId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    window.alert(await readError(response, "删除失败。"));
    return;
  }
  await loadComments();
  refreshCourseFileCounts();
}

