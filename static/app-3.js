async function loadUsers(page = 1) {
  if (!userList) return;
  currentUserPage = page;
  // 勾选只在当前这一页有效：翻页或换筛选条件后清空，避免改到看不见的用户。
  selectedUserIds.clear();
  showState(userList, "正在加载用户...");
  userPagination.innerHTML = "";
  try {
    const response = await fetch(`/api/users?${userQuery(page)}`);
    if (!response.ok) throw new Error(await readError(response, "用户列表加载失败。"));
    renderUsers(await response.json());
  } catch (error) {
    showState(userList, error.message || "用户列表加载失败。", true);
    userPagination.innerHTML = "";
  }
}

function renderUsers(data) {
  const users = data.items || [];
  userList.innerHTML = "";
  currentUserIds = users.map((item) => item.id);
  if (!users.length) {
    showState(userList, "没有匹配的用户");
    renderPagination(userPagination, null, () => {});
    syncUserSelection();
    return;
  }
  users.forEach((item) => userList.append(renderUserRow(item)));
  renderPagination(userPagination, data, (page) => loadUsers(page));
  syncUserSelection();
}

function syncUserSelection() {
  const count = selectedUserIds.size;
  if (userSelectionCount) {
    userSelectionCount.textContent = count ? `已选 ${count} 个` : "";
  }
  [userBatchEnable, userBatchDisable, userBatchRoleApply].forEach((button) => {
    if (button) button.disabled = count === 0;
  });
  if (userBatchRole) userBatchRole.disabled = count === 0;
  if (userSelectAll) {
    const onPage = currentUserIds.filter((id) => selectedUserIds.has(id)).length;
    userSelectAll.checked = currentUserIds.length > 0 && onPage === currentUserIds.length;
    // 只选了一部分时用「半选」状态，避免看起来像全选或全不选。
    userSelectAll.indeterminate = onPage > 0 && onPage < currentUserIds.length;
  }
}

function setUserBatchMessage(message, isError = false) {
  if (!userBatchMessage) return;
  userBatchMessage.textContent = message;
  userBatchMessage.className = isError ? "form-message error-message" : "form-message";
}

// 批量操作逐条回报，这里把「哪几条失败、为什么」拼成一句人话。
function describeBatchResult(noun, result) {
  if (!result.failed) {
    return `${noun}批量操作完成：成功 ${result.succeeded} 条。`;
  }
  const reasons = (result.items || [])
    .filter((item) => !item.ok)
    .map((item) => `#${item.id} ${item.message}`)
    .join("；");
  return `${noun}批量操作完成：成功 ${result.succeeded} 条，失败 ${result.failed} 条（${reasons}）`;
}

async function batchUserAction(action, role = null) {
  const ids = [...selectedUserIds];
  if (!ids.length) return;
  const payload = { ids, action };
  if (role) payload.role = role;
  setUserBatchMessage("正在处理...");
  try {
    const response = await fetch("/api/users/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await readError(response, "批量操作失败。"));
    const result = await response.json();
    setUserBatchMessage(describeBatchResult("用户", result), result.failed > 0);
    selectedUserIds.clear();
    await loadUsers(currentUserPage);
  } catch (error) {
    setUserBatchMessage(error.message || "批量操作失败。", true);
  }
}

async function loadAudit(page = 1) {
  if (!auditList) return;
  currentAuditPage = page;
  showState(auditList, "正在加载操作记录...");
  auditPagination.innerHTML = "";
  try {
    const response = await fetch(`/api/audit?${auditQuery(page)}`);
    if (!response.ok) throw new Error(await readError(response, "操作记录加载失败。"));
    renderAudit(await response.json());
  } catch (error) {
    showState(auditList, error.message || "操作记录加载失败。", true);
    auditPagination.innerHTML = "";
  }
}

function auditQuery(page) {
  const params = auditFilterParams();
  params.set("page", String(page));
  params.set("page_size", "10");
  return params;
}

// 审计的筛选条件。列表与导出共用，避免两边规则走偏。
function auditFilterParams() {
  const params = new URLSearchParams();
  const keyword = auditFilterKeyword.value.trim();
  if (keyword) params.set("关键词", keyword);
  if (auditFilterAction.value) params.set("动作", auditFilterAction.value);
  if (auditFilterEntity.value) params.set("对象", auditFilterEntity.value);
  return params;
}

function renderAudit(data) {
  const records = data.items || [];
  auditList.innerHTML = "";
  if (!records.length) {
    showState(auditList, "没有匹配的操作记录");
    renderPagination(auditPagination, null, () => {});
    return;
  }
  records.forEach((item) => auditList.append(renderAuditRow(item)));
  renderPagination(auditPagination, data, (page) => loadAudit(page));
}

function renderAuditRow(item) {
  const row = document.createElement("li");
  row.className = "user-row";

  const identity = document.createElement("div");
  identity.className = "user-identity";

  const title = document.createElement("h3");
  title.textContent = item.actor_name || "（账户已删除）";
  const actionBadge = document.createElement("span");
  actionBadge.className = "status-badge status-approved";
  actionBadge.textContent = AUDIT_ACTION_LABELS[item.action] || item.action;
  title.append(" ", actionBadge);

  const meta = document.createElement("p");
  meta.className = "user-meta";
  const target = AUDIT_ENTITY_LABELS[item.entity_type] || item.entity_type;
  const targetId = item.entity_id == null ? "" : ` #${item.entity_id}`;
  const detail = item.detail ? ` · ${item.detail}` : "";
  meta.textContent = `${target}${targetId} · ${formatDateTime(item.created_at)}${detail}`;

  identity.append(title, meta);
  row.append(identity);
  return row;
}

async function loadTrash(page = 1) {
  if (!trashList) return;
  currentTrashPage = page;
  // 勾选只在当前这一页有效：翻页或换筛选条件后清空，避免删到看不见的资料。
  selectedTrashIds.clear();
  setTrashBatchMessage("");
  showState(trashList, "正在加载回收站...");
  trashPagination.innerHTML = "";
  try {
    const response = await fetch(`/api/trash?${trashQuery(page)}`);
    if (!response.ok) throw new Error(await readError(response, "回收站加载失败。"));
    renderTrash(await response.json());
  } catch (error) {
    showState(trashList, error.message || "回收站加载失败。", true);
    trashPagination.innerHTML = "";
    currentTrashIds = [];
    syncTrashSelection();
  }
}

function trashQuery(page) {
  const params = new URLSearchParams({ page: String(page), page_size: "10" });
  const keyword = trashFilterKeyword.value.trim();
  if (keyword) params.set("关键词", keyword);
  return params;
}

function renderTrash(data) {
  const records = data.items || [];
  trashList.innerHTML = "";
  currentTrashIds = records.map((item) => item.id);
  if (!records.length) {
    showState(trashList, "回收站是空的");
    renderPagination(trashPagination, null, () => {});
    syncTrashSelection();
    return;
  }
  records.forEach((item) => trashList.append(renderTrashRow(item)));
  renderPagination(trashPagination, data, (page) => loadTrash(page));
  syncTrashSelection();
}

function renderTrashRow(item) {
  const row = document.createElement("li");
  row.className = "user-row";

  const select = document.createElement("input");
  select.type = "checkbox";
  select.className = "file-select";
  select.checked = selectedTrashIds.has(item.id);
  select.setAttribute("aria-label", `选择回收站资料 ${item.title}`);
  select.addEventListener("change", () => {
    if (select.checked) selectedTrashIds.add(item.id);
    else selectedTrashIds.delete(item.id);
    syncTrashSelection();
  });

  const identity = document.createElement("div");
  identity.className = "user-identity";
  const title = document.createElement("h3");
  title.textContent = item.title;
  const badge = document.createElement("span");
  badge.className = "status-badge status-inactive";
  badge.textContent = "已删除";
  title.append(" ", badge);

  const meta = document.createElement("p");
  meta.className = "user-meta";
  const course = item.course_name || "（课程已删除）";
  const deleter = item.deleted_by_name || "（账户已删除）";
  meta.textContent =
    `${item.original_name} · ${formatFileSize(item.size)} · ` +
    `课程：${course} · 由 ${deleter} 于 ${formatDateTime(item.deleted_at)} 删除`;
  identity.append(title, meta);

  const actions = document.createElement("div");
  actions.className = "user-actions";

  const restore = document.createElement("button");
  restore.type = "button";
  restore.className = "text-button";
  restore.textContent = "恢复";
  restore.addEventListener("click", () => restoreTrashFile(item));

  const purge = document.createElement("button");
  purge.type = "button";
  purge.className = "text-button danger-button";
  purge.textContent = "彻底删除";
  purge.addEventListener("click", () => purgeTrashFile(item));

  actions.append(restore, purge);
  row.append(select, identity, actions);
  return row;
}

function syncTrashSelection() {
  const count = selectedTrashIds.size;
  if (trashSelectionCount) {
    trashSelectionCount.textContent = count ? `已选 ${count} 个` : "";
  }
  if (trashBatchRestore) trashBatchRestore.disabled = count === 0;
  if (trashBatchPurge) trashBatchPurge.disabled = count === 0;
  if (trashSelectAll) {
    const onPage = currentTrashIds.filter((id) => selectedTrashIds.has(id)).length;
    trashSelectAll.checked =
      currentTrashIds.length > 0 && onPage === currentTrashIds.length;
    // 只选了一部分时用「半选」状态，避免看起来像全选或全不选。
    trashSelectAll.indeterminate =
      onPage > 0 && onPage < currentTrashIds.length;
  }
}

function setTrashBatchMessage(message, isError = false) {
  if (!trashBatchMessage) return;
  trashBatchMessage.textContent = message;
  trashBatchMessage.className = isError ? "form-message error-message" : "form-message";
}

async function batchTrashAction(kind) {
  const ids = [...selectedTrashIds];
  if (!ids.length) return;
  const restore = kind === "restore";
  if (!restore) {
    const confirmed = window.confirm(
      `彻底删除选中的 ${ids.length} 份资料吗？文件会从磁盘上真正删除，之后无法再恢复。`
    );
    if (!confirmed) return;
  }
  setTrashBatchMessage("正在处理...");
  const body = JSON.stringify({ ids });
  try {
    // 两个分支各写一条 fetch：路径与方法都必须是字面量，
    // 否则 tests/test_frontend_contract.py 的前后端接口一致性测试扫不到这次调用。
    const response = restore
      ? await fetch("/api/trash/batch/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        })
      : await fetch("/api/trash/batch/purge", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        });
    if (!response.ok) throw new Error(await readError(response, "批量操作失败。"));
    const result = await response.json();
    setTrashBatchMessage(describeBatchResult("回收站", result), result.failed > 0);
    selectedTrashIds.clear();
    await loadTrash(currentTrashPage);
  } catch (error) {
    setTrashBatchMessage(error.message || "批量操作失败。", true);
  }
}

async function restoreTrashFile(item) {
  const response = await fetch(`/api/trash/${encodeURIComponent(item.id)}/restore`, {
    method: "POST",
  });
  if (!response.ok) {
    window.alert(await readError(response, "恢复失败。"));
    return;
  }
  await loadTrash(currentTrashPage);
}

async function purgeTrashFile(item) {
  const confirmed = window.confirm(
    `彻底删除“${item.title}”吗？文件会从磁盘上真正删除，之后无法再恢复。`
  );
  if (!confirmed) return;
  const response = await fetch(`/api/trash/${encodeURIComponent(item.id)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    window.alert(await readError(response, "彻底删除失败。"));
    return;
  }
  await loadTrash(currentTrashPage);
}

function renderUserRow(item) {
  const isSelf = item.id === currentUser?.id;
  const row = document.createElement("li");
  row.className = "user-row";

  const select = document.createElement("input");
  select.type = "checkbox";
  select.className = "file-select";
  select.checked = selectedUserIds.has(item.id);
  select.setAttribute("aria-label", `选择用户 ${item.username}`);
  select.addEventListener("change", () => {
    if (select.checked) selectedUserIds.add(item.id);
    else selectedUserIds.delete(item.id);
    syncUserSelection();
  });

  const identity = document.createElement("div");
  identity.className = "user-identity";
  const title = document.createElement("h3");
  title.textContent = item.username;
  if (isSelf) {
    const selfTag = document.createElement("span");
    selfTag.className = "user-self-tag";
    selfTag.textContent = "当前账户";
    title.append(" ", selfTag);
  }
  const stateBadge = document.createElement("span");
  stateBadge.className = `status-badge ${item.is_active ? "status-approved" : "status-inactive"}`;
  stateBadge.textContent = item.is_active ? "已启用" : "已停用";
  title.append(" ", stateBadge);
  const meta = document.createElement("p");
  meta.className = "user-meta";
  const created = item.created_at
    ? ` · 创建于 ${formatDateTime(item.created_at)}`
    : "";
  meta.textContent = `角色：${ROLE_LABELS[item.role] || item.role} · 上传 ${item.upload_count} 份资料${created}`;
  identity.append(title, meta);

  const actions = document.createElement("div");
  actions.className = "user-actions";

  const roleSelect = document.createElement("select");
  Object.entries(ROLE_LABELS).forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.selected = value === item.role;
    roleSelect.append(option);
  });
  roleSelect.disabled = isSelf;
  if (isSelf) roleSelect.title = "不能修改自己的角色";
  roleSelect.setAttribute("aria-label", `${item.username} 的角色`);
  roleSelect.addEventListener("change", () => changeUserRole(item, roleSelect));

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = item.is_active ? "text-button danger-button" : "text-button";
  toggle.textContent = item.is_active ? "停用" : "启用";
  toggle.disabled = isSelf && item.is_active;
  if (toggle.disabled) toggle.title = "不能停用当前登录的账户";
  toggle.addEventListener("click", () => toggleUserActive(item));

  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "text-button";
  reset.textContent = "重置密码";
  reset.addEventListener("click", () => resetUserPassword(item));

  actions.append(roleSelect, toggle, reset);
  row.append(select, identity, actions);
  return row;
}

async function createUser(event) {
  event.preventDefault();
  userCreateMessage.textContent = "正在创建...";
  userCreateMessage.className = "form-message";
  const submitButton = userCreateForm.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const response = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(userCreateForm))),
    });
    if (!response.ok) throw new Error(await readError(response, "用户创建失败。"));
    userCreateForm.reset();
    userCreateMessage.textContent = "用户创建成功。";
    userCreateMessage.className = "form-message success-message";
    await loadUsers(1);
  } catch (error) {
    userCreateMessage.textContent = error.message || "用户创建失败。";
    userCreateMessage.className = "form-message error-message";
  } finally {
    submitButton.disabled = false;
  }
}

async function patchUser(item, payload, fallback) {
  const response = await fetch(`/api/users/${encodeURIComponent(item.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    window.alert(await readError(response, fallback));
    return false;
  }
  await loadUsers(currentUserPage);
  return true;
}

async function changeUserRole(item, select) {
  const role = select.value;
  if (role === item.role) return;
  const label = ROLE_LABELS[role] || role;
  if (!window.confirm(`确定把“${item.username}”的角色改为${label}吗？`)) {
    select.value = item.role;
    return;
  }
  if (!(await patchUser(item, { role }, "角色修改失败。"))) select.value = item.role;
}

async function toggleUserActive(item) {
  const action = item.is_active ? "停用" : "启用";
  const extra = item.is_active ? "，该用户已登录的会话会立即失效" : "";
  if (!window.confirm(`确定${action}“${item.username}”吗？${extra}`)) return;
  await patchUser(item, { is_active: !item.is_active }, `${action}失败。`);
}

async function resetUserPassword(item) {
  const password = window.prompt(`请输入“${item.username}”的新密码（至少 8 位）`);
  if (password === null) return;
  if (password.length < 8) {
    window.alert("新密码至少需要 8 位。");
    return;
  }
  const response = await fetch(`/api/users/${encodeURIComponent(item.id)}/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "密码重置失败。"));
    return;
  }
  userCreateMessage.textContent = `已重置“${item.username}”的密码，该用户需要重新登录。`;
  userCreateMessage.className = "form-message success-message";
}

async function loadMyUploads(page = 1) {
  if (!myUploadsList) return;
  currentMyUploadPage = page;
  showState(myUploadsList, "正在加载...");
  myUploadsCount.textContent = "";
  myUploadsPagination.innerHTML = "";
  const params = new URLSearchParams({ page: String(page), page_size: "10" });
  if (myUploadsStatus.value) params.set("状态", myUploadsStatus.value);
  try {
    const response = await fetch(`/api/my-files?${params}`);
    if (!response.ok) throw new Error(await readError(response, "我的上传加载失败。"));
    renderMyUploads(await response.json());
  } catch (error) {
    showState(myUploadsList, error.message || "我的上传加载失败。", true);
  }
}

function renderMyUploads(data) {
  const files = data.items || [];
  myUploadsList.innerHTML = "";
  myUploadsCount.textContent = `${data.total} 份`;
  if (!files.length) {
    showState(myUploadsList, "还没有上传记录，去课程页上传第一份资料吧。");
    renderPagination(myUploadsPagination, null, () => {});
    return;
  }
  files.forEach((file) => myUploadsList.append(renderMyUploadRow(file)));
  renderPagination(myUploadsPagination, data, (page) => loadMyUploads(page));
}

function renderMyUploadRow(file) {
  const item = document.createElement("li");
  item.className = "file-row";

  const details = document.createElement("div");
  details.className = "file-details";
  const titleLine = document.createElement("div");
  titleLine.className = "file-title-line";
  const title = document.createElement("h3");
  title.textContent = file.title;
  titleLine.append(title, statusBadge(file.status));
  const metadata = document.createElement("p");
  metadata.className = "file-meta";
  metadata.textContent = `${file.original_name} · ${formatFileSize(file.size)} · ${formatDateTime(file.upload_time) || "上传时间未知"}`;
  const course = document.createElement("p");
  course.className = "file-meta";
  course.textContent = `所属课程：${file.course?.name || "未知课程"}`;
  details.append(titleLine, metadata, course);

  const actions = document.createElement("div");
  actions.className = "file-actions";
  const preview = previewButton(file);
  if (preview) actions.append(preview);
  if (file.status !== "approved") {
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "text-button";
    edit.textContent = "编辑标题";
    edit.addEventListener("click", () => editMyUpload(file));
    const withdraw = document.createElement("button");
    withdraw.type = "button";
    withdraw.className = "text-button danger-button";
    withdraw.textContent = file.status === "pending" ? "撤回" : "删除";
    withdraw.addEventListener("click", () => withdrawMyUpload(file));
    actions.append(edit, withdraw);
  }
  const download = document.createElement("a");
  download.className = "download-link";
  download.href = `/api/files/${encodeURIComponent(file.id)}/download`;
  download.textContent = "下载";
  download.setAttribute("download", "");
  actions.append(download);

  item.append(details, actions);
  return item;
}

async function editMyUpload(file) {
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
  await loadMyUploads(currentMyUploadPage);
}

async function withdrawMyUpload(file) {
  const action = file.status === "pending" ? "撤回" : "删除";
  if (!window.confirm(`确定${action}“${file.title}”吗？该资料会从课程中移除。`)) return;
  const response = await fetch(`/api/files/${encodeURIComponent(file.id)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    window.alert(await readError(response, `${action}失败。`));
    return;
  }
  await loadMyUploads(currentMyUploadPage);
}

function readError(response, fallback) {
  return response.json()
    .then((body) => body.error?.message || body.detail || fallback)
    .catch(() => fallback);
}

function initAuth() {
  loginToggle?.addEventListener("click", toggleLoginPanel);
  authHintLogin?.addEventListener("click", () => {
    if (loginPanel?.hidden) toggleLoginPanel();
  });
  logoutButton?.addEventListener("click", logout);
  loginForm?.addEventListener("submit", submitLogin);
  passwordToggle?.addEventListener("click", togglePasswordPanel);
  passwordForm?.addEventListener("submit", submitPasswordChange);
  previewClose?.addEventListener("click", closePreview);
  previewDialog?.querySelector("[data-preview-close]")?.addEventListener("click", closePreview);
  commentClose?.addEventListener("click", closeComments);
  commentDialog?.querySelector("[data-comment-close]")?.addEventListener("click", closeComments);
  commentForm?.addEventListener("submit", submitComment);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePreview();
      closeComments();
    }
  });
}

function initHomePage() {
  // 热门 / 最新是公开内容，进首页就加载。
  loadInsights();
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });
  [searchCourse, searchType, searchStart, searchEnd, searchSort].forEach((control) => {
    control?.addEventListener("change", () => runSearch());
  });
  searchResetButton?.addEventListener("click", resetSearchFilters);
  courseCreateForm?.addEventListener("submit", createCourse);
  userCreateForm?.addEventListener("submit", createUser);
  userFilterButton?.addEventListener("click", () => loadUsers(1));
  userSelectAll?.addEventListener("change", () => {
    // 只作用于当前这一页；跨页的勾选状态保持不变。
    currentUserIds.forEach((id) => {
      if (userSelectAll.checked) selectedUserIds.add(id);
      else selectedUserIds.delete(id);
    });
    userList.querySelectorAll(".file-select").forEach((box) => {
      box.checked = userSelectAll.checked;
    });
    syncUserSelection();
  });
  userBatchEnable?.addEventListener("click", () => {
    if (window.confirm(`确定启用选中的 ${selectedUserIds.size} 个用户吗？`)) {
      batchUserAction("enable");
    }
  });
  userBatchDisable?.addEventListener("click", () => {
    if (window.confirm(`确定停用选中的 ${selectedUserIds.size} 个用户吗？停用后他们会立即被登出。`)) {
      batchUserAction("disable");
    }
  });
  userBatchRoleApply?.addEventListener("click", () => {
    if (!userBatchRole?.value) {
      setUserBatchMessage("请先选择要批量设置的角色。", true);
      return;
    }
    const label = userBatchRole.options[userBatchRole.selectedIndex].textContent;
    if (window.confirm(`确定把选中的 ${selectedUserIds.size} 个用户都改成「${label}」吗？`)) {
      batchUserAction("role", userBatchRole.value);
    }
  });
  userBatchRole?.addEventListener("change", () => setUserBatchMessage(""));
  userFilterRole?.addEventListener("change", () => loadUsers(1));
  userFilterKeyword?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    loadUsers(1);
  });
  auditFilterButton?.addEventListener("click", () => loadAudit(1));
  exportAuditButton?.addEventListener("click", exportAuditLogs);
  auditFilterAction?.addEventListener("change", () => loadAudit(1));
  auditFilterEntity?.addEventListener("change", () => loadAudit(1));
  auditFilterKeyword?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    loadAudit(1);
  });
  trashFilterButton?.addEventListener("click", () => loadTrash(1));
  trashFilterKeyword?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    loadTrash(1);
  });
  trashSelectAll?.addEventListener("change", () => {
    // 只作用于当前这一页；跨页的勾选状态保持不变。
    currentTrashIds.forEach((id) => {
      if (trashSelectAll.checked) selectedTrashIds.add(id);
      else selectedTrashIds.delete(id);
    });
    trashList.querySelectorAll(".file-select").forEach((box) => {
      box.checked = trashSelectAll.checked;
    });
    syncTrashSelection();
  });
  trashBatchRestore?.addEventListener("click", () => batchTrashAction("restore"));
  trashBatchPurge?.addEventListener("click", () => batchTrashAction("purge"));
  myUploadsStatus?.addEventListener("change", () => loadMyUploads(1));
  myUploadsRefreshButton?.addEventListener("click", () => loadMyUploads(currentMyUploadPage));

  const params = new URLSearchParams(window.location.search);
  const query = (params.get("q") || params.get("关键词"))?.trim() || "";
  if (searchCourse) searchCourse.value = params.get("课程编号") || "";
  if (searchType) searchType.value = params.get("类型") || "";
  if (searchStart) searchStart.value = params.get("起始时间") || "";
  if (searchEnd) searchEnd.value = params.get("结束时间") || "";
  if (searchSort) searchSort.value = params.get("排序") || "newest";
  populateCourseFilter();
  if (query) searchInput.value = query;
  if (query || activeFilterCount()) runCombinedSearch(1);
  else loadCourses();
}

async function initCoursePage() {
  const params = new URLSearchParams(window.location.search);
  currentCourseId = params.get("id") || params.get("编号");
  courseName.textContent = "正在加载课程...";
  courseContext.textContent = currentCourseId ? "课程资料共享" : "缺少课程信息";
  if (!currentCourseId || !/^\d+$/.test(currentCourseId)) {
    showState(fileList, "无法识别这门课程，请从首页重新进入。", true);
    uploadForm.hidden = true;
    return;
  }
  uploadForm.addEventListener("submit", (event) => uploadFiles(currentCourseId, event));
  fileInput.addEventListener("change", updateFileSelection);
  initDropZone();
  selectedFileIds.clear();
  initArchiveControls();
  try {
    const response = await fetch(`/api/courses/${encodeURIComponent(currentCourseId)}`);
    if (!response.ok) throw new Error("课程不存在");
    currentCourse = await response.json();
    courseName.textContent = currentCourse.name;
    courseContext.textContent = courseContextText(currentCourse);
    renderCourseActions(currentCourse);
    await loadCourseFiles(currentCourseId);
  } catch (error) {
    courseName.textContent = "课程不存在";
    courseContext.textContent = error.message;
    uploadForm.hidden = true;
  }
}

function insightRow(file) {
  const item = document.createElement("li");
  item.className = "file-row";

  const details = document.createElement("div");
  details.className = "file-details";
  const title = document.createElement("h3");
  title.textContent = file.title;
  const meta = document.createElement("p");
  meta.className = "file-meta";
  const course = file.course?.name || "未知课程";
  meta.textContent = `${course} · ${file.original_name} · ${formatFileSize(file.size)} · 下载 ${file.download_count} 次`;
  details.append(title, meta);

  const actions = document.createElement("div");
  actions.className = "file-actions";
  const courseLink = document.createElement("a");
  courseLink.className = "course-link";
  courseLink.href = courseUrl(file.course);
  courseLink.textContent = "查看课程";
  const download = document.createElement("a");
  download.className = "download-link";
  download.href = `/api/files/${encodeURIComponent(file.id)}/download`;
  download.textContent = "下载";
  download.setAttribute("download", "");
  actions.append(courseLink, download);

  item.append(details, actions);
  return item;
}

async function loadInsightList(list, url) {
  if (!list) return;
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error("加载失败。");
    const data = await response.json();
    list.innerHTML = "";
    if (!data.items.length) {
      showState(list, "暂时没有可展示的资料。");
      return;
    }
    data.items.forEach((file) => list.append(insightRow(file)));
  } catch (error) {
    showState(list, error.message || "加载失败。", true);
  }
}

function loadInsights() {
  loadInsightList(hotList, "/api/hot");
  loadInsightList(recentList, "/api/recent");
}

async function loadOverview() {
  if (!overviewList) return;
  try {
    const response = await fetch("/api/overview");
    if (!response.ok) throw new Error(await readError(response, "概览加载失败。"));
    const data = await response.json();
    const rows = [
      ["课程数", data.courses],
      [
        "资料",
        `已通过 ${data.files.approved} · 待审核 ${data.files.pending} · 已拒绝 ${data.files.rejected}`,
      ],
      ["回收站", data.trash],
      ["用户", `启用 ${data.users_active} / 共 ${data.users_total}`],
      ["存储用量", formatFileSize(data.storage_bytes)],
      ["下载总数", data.downloads],
    ];
    overviewList.innerHTML = "";
    rows.forEach(([label, value]) => {
      const item = document.createElement("li");
      item.className = "overview-row";
      const name = document.createElement("span");
      name.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = String(value);
      item.append(name, strong);
      overviewList.append(item);
    });
  } catch (error) {
    showState(overviewList, error.message || "概览加载失败。", true);
  }
}

function formatSessionLine(session) {
  const created = formatDateTime(session.created_at) || session.created_at;
  const expires = formatDateTime(session.expires_at) || session.expires_at;
  const parts = [`登录于 ${created}`, `有效期至 ${expires}`];
  if (session.ip) parts.push(session.ip);
  return parts.join(" · ");
}

function renderSessions(items) {
  sessionsList.innerHTML = "";
  if (!items.length) {
    showState(sessionsList, "没有登录记录。");
    return;
  }
  items.forEach((session) => {
    const item = document.createElement("li");
    item.className = "record-row";
    const details = document.createElement("div");
    details.className = "file-details";
    const title = document.createElement("p");
    title.className = "file-meta";
    title.textContent = `${session.user_agent || "未知设备"}${session.current ? "（当前设备）" : ""}`;
    const meta = document.createElement("p");
    meta.className = "file-meta";
    meta.textContent = formatSessionLine(session);
    details.append(title, meta);
    item.append(details);
    if (!session.current) {
      const actions = document.createElement("div");
      actions.className = "file-actions";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "text-button danger-button";
      button.textContent = "退出该设备";
      button.addEventListener("click", () => revokeSession(session.id));
      actions.append(button);
      item.append(actions);
    }
    sessionsList.append(item);
  });
}

async function loadSessions() {
  if (!sessionsList) return;
  try {
    const response = await fetch("/api/my-sessions");
    if (!response.ok) throw new Error(await readError(response, "登录设备加载失败。"));
    renderSessions((await response.json()).items || []);
  } catch (error) {
    showState(sessionsList, error.message || "登录设备加载失败。", true);
  }
}

async function revokeSession(sessionId) {
  if (!window.confirm("确定退出该设备吗？")) return;
  const response = await fetch(
    `/api/my-sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    window.alert(await readError(response, "退出失败。"));
    return;
  }
  loadSessions();
}

async function bootstrap() {
  initAuth();
  await loadCurrentUser();
  if (courseList) initHomePage();
  if (fileList) await initCoursePage();
}

bootstrap();
