const courseList = document.querySelector("#course-list");
const courseCount = document.querySelector("#course-count");
const coursePagination = document.querySelector("#course-pagination");
const courseHeading = document.querySelector("#course-heading");
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#search-input");
const searchButton = searchForm?.querySelector("button");
const courseName = document.querySelector("#course-name");
const courseContext = document.querySelector("#course-context");
const fileList = document.querySelector("#file-list");
const fileCount = document.querySelector("#file-count");
const filePagination = document.querySelector("#file-pagination");
const courseActions = document.querySelector("#course-actions");
const uploadForm = document.querySelector("#upload-form");
const uploadButton = document.querySelector("#upload-button");
const uploadMessage = document.querySelector("#upload-message");
const uploadAccessNote = document.querySelector("#upload-access-note");
const fileInput = document.querySelector("#file-input");
const fileSelection = document.querySelector("#file-selection");
const uploadProgress = document.querySelector("#upload-progress");
const uploadProgressLabel = document.querySelector("#upload-progress-label");
const uploadResults = document.querySelector("#upload-results");
const dropZone = document.querySelector("#drop-zone");
const previewDialog = document.querySelector("#preview-dialog");
const previewTitle = document.querySelector("#preview-title");
const previewBody = document.querySelector("#preview-body");
const previewDownload = document.querySelector("#preview-download");
const previewClose = document.querySelector("#preview-close");
const authStatus = document.querySelector("#auth-status");
const loginToggle = document.querySelector("#login-toggle");
const logoutButton = document.querySelector("#logout-button");
const loginPanel = document.querySelector("#login-panel");
const authHint = document.querySelector("#auth-hint");
const authHintLogin = document.querySelector("#auth-hint-login");
const loginForm = document.querySelector("#login-form");
const loginMessage = document.querySelector("#login-message");
const adminCoursePanel = document.querySelector("#admin-course-panel");
const courseCreateForm = document.querySelector("#course-create-form");
const courseCreateMessage = document.querySelector("#course-create-message");
const adminUserPanel = document.querySelector("#admin-user-panel");
const userCreateForm = document.querySelector("#user-create-form");
const userCreateMessage = document.querySelector("#user-create-message");
const userList = document.querySelector("#user-list");
const userPagination = document.querySelector("#user-pagination");
const userFilterKeyword = document.querySelector("#user-filter-keyword");
const userFilterRole = document.querySelector("#user-filter-role");
const userFilterButton = document.querySelector("#user-filter-button");
const myUploadsPanel = document.querySelector("#my-uploads-panel");
const myUploadsList = document.querySelector("#my-uploads-list");
const myUploadsCount = document.querySelector("#my-uploads-count");
const myUploadsPagination = document.querySelector("#my-uploads-pagination");
const myUploadsStatus = document.querySelector("#my-uploads-status");
const myUploadsRefreshButton = document.querySelector("#my-uploads-refresh");
const searchCourse = document.querySelector("#search-course");
const searchType = document.querySelector("#search-type");
const searchStart = document.querySelector("#search-start");
const searchEnd = document.querySelector("#search-end");
const searchSort = document.querySelector("#search-sort");
const searchResetButton = document.querySelector("#search-reset");

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ROLE_LABELS = { admin: "管理员", uploader: "上传者", viewer: "浏览者" };
const STATUS_LABELS = { approved: "已通过", pending: "待审核", rejected: "已拒绝" };
// 与后端 PREVIEW_MEDIA_TYPES 保持一致，只预览确定不会执行脚本的类型。
const PREVIEW_IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif"]);
const PREVIEW_DOCUMENT_EXTENSIONS = new Set(["pdf", "txt", "md"]);
let currentUser = null;
let currentCourse = null;
let currentCourseId = null;
let currentFilePage = 1;
let currentUserPage = 1;
let currentMyUploadPage = 1;
let currentSearchQuery = "";

function showState(container, message, isError = false) {
  container.innerHTML = "";
  const element = document.createElement(container.tagName === "UL" ? "li" : "p");
  element.className = isError ? "state-message error-message" : "state-message";
  element.textContent = message;
  container.append(element);
}

function formatFileSize(size) {
  if (size < 1024) return `${size} 字节`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} 千字节`;
  return `${(size / (1024 * 1024)).toFixed(1)} 兆字节`;
}

// 接口返回的时间是 UTC 字符串（形如 "2026-10-07 12:17:18"），补上 Z 标明时区后再按浏览器本地时区展示。
// 直接显示原始字符串会让北京时间早 8 小时，所以任何时间字段都必须走这里。
function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(`${value.replace(" ", "T")}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}

function courseUrl(course) {
  return `/course?id=${encodeURIComponent(course.id)}`;
}

// 把命中的关键词片段包进 <mark>，按空格拆词、大小写不敏感。
function highlight(text, query) {
  const fragment = document.createDocumentFragment();
  const source = String(text ?? "");
  const terms = (query || "")
    .split(/\s+/)
    .map((term) => term.trim().toLowerCase())
    .filter(Boolean);
  if (!terms.length) {
    fragment.append(source);
    return fragment;
  }
  const lower = source.toLowerCase();
  let cursor = 0;
  while (cursor < source.length) {
    let hit = -1;
    let hitTerm = "";
    terms.forEach((term) => {
      const found = lower.indexOf(term, cursor);
      if (found === -1) return;
      if (hit === -1 || found < hit) {
        hit = found;
        hitTerm = term;
      }
    });
    if (hit === -1) {
      fragment.append(source.slice(cursor));
      break;
    }
    if (hit > cursor) fragment.append(source.slice(cursor, hit));
    const mark = document.createElement("mark");
    mark.textContent = source.slice(hit, hit + hitTerm.length);
    fragment.append(mark);
    cursor = hit + hitTerm.length;
  }
  return fragment;
}

function renderPagination(container, data, onPage) {
  container.innerHTML = "";
  if (!data || data.total_pages <= 1) return;
  const previous = document.createElement("button");
  previous.type = "button";
  previous.textContent = "上一页";
  previous.disabled = data.page <= 1;
  previous.addEventListener("click", () => onPage(data.page - 1));
  const pageStatus = document.createElement("span");
  pageStatus.textContent = `${data.page} / ${data.total_pages}`;
  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "下一页";
  next.disabled = data.page >= data.total_pages;
  next.addEventListener("click", () => onPage(data.page + 1));
  container.append(previous, pageStatus, next);
}

function updateAuthUI() {
  if (!authStatus) return;
  authStatus.textContent = currentUser
    ? `${currentUser.username} · ${ROLE_LABELS[currentUser.role] || currentUser.role}`
    : "未登录";
  loginToggle.hidden = Boolean(currentUser);
  logoutButton.hidden = !currentUser;
  if (authHint) authHint.hidden = Boolean(currentUser);
  if (loginPanel && currentUser) loginPanel.hidden = true;
  if (adminCoursePanel) adminCoursePanel.hidden = currentUser?.role !== "admin";
  if (adminUserPanel) adminUserPanel.hidden = currentUser?.role !== "admin";
  if (myUploadsPanel) myUploadsPanel.hidden = !currentUser;
  updateUploadAccess();
  if (currentCourse) renderCourseActions(currentCourse);
  ensureUserPanelLoaded();
  ensureMyUploadsLoaded();
}

function ensureUserPanelLoaded() {
  if (!adminUserPanel || currentUser?.role !== "admin") return;
  if (adminUserPanel.dataset.loaded === "1") return;
  adminUserPanel.dataset.loaded = "1";
  loadUsers(1);
}

function ensureMyUploadsLoaded() {
  if (!myUploadsPanel || !currentUser) return;
  if (myUploadsPanel.dataset.loaded === "1") return;
  myUploadsPanel.dataset.loaded = "1";
  loadMyUploads(1);
}

// 切换账户时必须丢掉上一个账户的加载标记，否则会沿用旧列表。
function resetPanelLoadFlags() {
  adminUserPanel?.removeAttribute("data-loaded");
  myUploadsPanel?.removeAttribute("data-loaded");
}

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/me");
    currentUser = response.ok ? await response.json() : null;
  } catch (error) {
    currentUser = null;
  }
  updateAuthUI();
}

function toggleLoginPanel() {
  if (!loginPanel) return;
  loginPanel.hidden = !loginPanel.hidden;
  if (!loginPanel.hidden) document.querySelector("#login-username")?.focus();
}

async function submitLogin(event) {
  event.preventDefault();
  loginMessage.textContent = "正在登录...";
  loginMessage.className = "form-message";
  const submitButton = loginForm.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(loginForm))),
    });
    if (!response.ok) throw new Error(await readError(response, "登录失败，请检查账户信息。"));
    currentUser = await response.json();
    loginForm.reset();
    loginMessage.textContent = "登录成功。";
    loginMessage.className = "form-message success-message";
    resetPanelLoadFlags();
    updateAuthUI();
    if (currentCourseId) await loadCourseFiles(currentCourseId, currentFilePage);
  } catch (error) {
    loginMessage.textContent = error.message || "登录失败，请稍后重试。";
    loginMessage.className = "form-message error-message";
  } finally {
    submitButton.disabled = false;
  }
}

async function logout() {
  logoutButton.disabled = true;
  try {
    await fetch("/api/logout", { method: "POST" });
  } finally {
    currentUser = null;
    resetPanelLoadFlags();
    updateAuthUI();
    if (currentCourseId) await loadCourseFiles(currentCourseId, currentFilePage);
    logoutButton.disabled = false;
  }
}

function renderCourses(data) {
  const courses = data.items || [];
  courseList.innerHTML = "";
  courseHeading.textContent = "全部课程";
  courseCount.textContent = `${data.total} 门`;
  if (!courses.length) {
    showState(courseList, "还没有课程资料");
    renderPagination(coursePagination, null, () => {});
    return;
  }
  courses.forEach((course) => {
    const card = document.createElement("a");
    card.className = "course-card";
    card.href = courseUrl(course);
    const title = document.createElement("h3");
    title.textContent = course.name;
    card.append(title);
    if (course.college) {
      const college = document.createElement("p");
      college.className = "course-meta";
      college.textContent = course.college;
      card.append(college);
    }
    if (course.semester) {
      const semester = document.createElement("p");
      semester.className = "course-meta";
      semester.textContent = course.semester;
      card.append(semester);
    }
    courseList.append(card);
  });
  renderPagination(coursePagination, data, (page) => loadCourses(page));
}

function renderSearchResults(data) {
  const results = data.items || [];
  courseList.innerHTML = "";
  courseHeading.textContent = "搜索结果";
  courseCount.textContent = `${data.total} 份`;
  if (!results.length) {
    showState(courseList, "没有找到相关资料");
    renderPagination(coursePagination, null, () => {});
    return;
  }
  results.forEach((file) => {
    const card = document.createElement("article");
    card.className = "search-result-card";
    const title = document.createElement("h3");
    title.append(highlight(file.title, currentSearchQuery));
    const metadata = document.createElement("p");
    metadata.className = "course-meta";
    metadata.append(highlight(file.original_name, currentSearchQuery));
    metadata.append(` · ${formatFileSize(file.size)}`);
    const course = document.createElement("p");
    course.className = "result-course";
    course.append("所属课程：");
    course.append(highlight(file.course.name, currentSearchQuery));
    const actions = document.createElement("div");
    actions.className = "result-actions";
    const courseLink = document.createElement("a");
    courseLink.className = "course-link";
    courseLink.href = courseUrl(file.course);
    courseLink.textContent = "查看课程";
    const preview = previewButton(file);
    if (preview) actions.append(preview);
    const download = document.createElement("a");
    download.className = "download-link";
    download.href = `/api/files/${encodeURIComponent(file.id)}/download`;
    download.textContent = "下载";
    download.setAttribute("download", "");
    actions.append(courseLink, download);
    card.append(title, metadata, course, actions);
    courseList.append(card);
  });
  renderPagination(coursePagination, data, (page) => searchFiles(searchInput.value.trim(), page));
}

function setSearchLoading(isLoading) {
  searchButton.disabled = isLoading;
  searchButton.textContent = isLoading ? "搜索中..." : "搜索";
}

async function loadCourses(page = 1) {
  showState(courseList, "正在加载课程...");
  courseCount.textContent = "";
  coursePagination.innerHTML = "";
  try {
    const response = await fetch(`/api/courses?page=${page}&page_size=12`);
    if (!response.ok) throw new Error("课程加载失败");
    renderCourses(await response.json());
  } catch (error) {
    showState(courseList, "课程加载失败，请稍后重试。", true);
    courseHeading.textContent = "全部课程";
    courseCount.textContent = "";
  }
}

function activeFilterCount() {
  return [searchCourse?.value, searchType?.value, searchStart?.value, searchEnd?.value]
    .filter(Boolean).length;
}

function searchFilterParams() {
  const params = new URLSearchParams();
  if (searchCourse?.value) params.set("课程编号", searchCourse.value);
  if (searchType?.value) params.set("类型", searchType.value);
  if (searchStart?.value) params.set("起始时间", searchStart.value);
  if (searchEnd?.value) params.set("结束时间", searchEnd.value);
  if (searchSort?.value) params.set("排序", searchSort.value);
  return params;
}

async function searchFiles(query, page = 1) {
  currentSearchQuery = query;
  showState(courseList, "正在搜索资料...");
  courseHeading.textContent = query ? "搜索结果" : "筛选结果";
  courseCount.textContent = "";
  coursePagination.innerHTML = "";
  setSearchLoading(true);
  try {
    const params = searchFilterParams();
    params.set("q", query);
    params.set("page", String(page));
    params.set("page_size", "12");
    const response = await fetch(`/api/search?${params}`);
    if (!response.ok) throw new Error(await readError(response, "搜索失败"));
    renderSearchResults(await response.json());
  } catch (error) {
    showState(courseList, `${error.message || "搜索失败"}，请检查筛选条件后重试。`, true);
    courseCount.textContent = "";
  } finally {
    setSearchLoading(false);
  }
}

function runSearch() {
  const query = searchInput.value.trim();
  const url = new URL(window.location.href);
  if (query) url.searchParams.set("q", query);
  else url.searchParams.delete("q");
  ["课程编号", "类型", "起始时间", "结束时间", "排序"].forEach((key) => url.searchParams.delete(key));
  searchFilterParams().forEach((value, key) => url.searchParams.set(key, value));
  window.history.replaceState({}, "", `${url.pathname}${url.search}`);
  if (query || activeFilterCount()) searchFiles(query, 1);
  else loadCourses();
}

function resetSearchFilters() {
  if (searchCourse) searchCourse.value = "";
  if (searchType) searchType.value = "";
  if (searchStart) searchStart.value = "";
  if (searchEnd) searchEnd.value = "";
  if (searchSort) searchSort.value = "newest";
  runSearch();
}

async function populateCourseFilter() {
  if (!searchCourse) return;
  try {
    const response = await fetch("/api/courses?page=1&page_size=100");
    if (!response.ok) return;
    const data = await response.json();
    (data.items || []).forEach((course) => {
      const option = document.createElement("option");
      option.value = course.id;
      option.textContent = course.name;
      searchCourse.append(option);
    });
  } catch (error) {
    // 课程下拉只是筛选辅助，加载失败时保持「全部课程」即可。
  }
}

function updateUploadAccess() {
  if (!uploadForm) return;
  const canUpload = currentUser && ["admin", "uploader"].includes(currentUser.role);
  uploadForm.hidden = !canUpload;
  uploadAccessNote.hidden = canUpload;
  if (!canUpload) {
    uploadAccessNote.textContent = currentUser ? "当前账户只有浏览权限。" : "登录后可以上传课程资料。";
  }
}

function statusBadge(status) {
  const badge = document.createElement("span");
  badge.className = `status-badge status-${status || "unknown"}`;
  badge.textContent = STATUS_LABELS[status] || "状态未知";
  return badge;
}

function canManageFile(file) {
  return currentUser?.role === "admin" || currentUser?.id === file.uploaded_by;
}

function renderFiles(data, courseId) {
  const files = data.items || [];
  fileList.innerHTML = "";
  fileCount.textContent = `${data.total} 份`;
  if (!files.length) {
    showState(fileList, "这个课程还没有资料，上传第一份吧。");
    renderPagination(filePagination, null, () => {});
    return;
  }
  files.forEach((file) => {
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
    const technical = document.createElement("p");
    technical.className = "file-meta file-technical";
    technical.textContent = `${file.mime_type || "未知类型"}${file.sha256 ? ` · SHA-256 ${file.sha256.slice(0, 12)}…` : ""}`;
    details.append(titleLine, metadata, technical);
    const download = document.createElement("a");
    download.className = "download-link";
    download.href = `/api/files/${encodeURIComponent(file.id)}/download`;
    download.textContent = "下载";
    download.setAttribute("download", "");
    const actions = document.createElement("div");
    actions.className = "file-actions";
    const preview = previewButton(file);
    if (preview) actions.append(preview);
    if (canManageFile(file)) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "text-button";
      edit.textContent = "编辑";
      edit.addEventListener("click", () => editFile(file, courseId));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "text-button danger-button";
      remove.textContent = "删除";
      remove.addEventListener("click", () => removeFile(file, courseId));
      actions.append(edit, remove);
    }
    if (currentUser?.role === "admin" && file.status !== "approved") {
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "text-button review-button";
      approve.textContent = "通过";
      approve.addEventListener("click", () => reviewFile(file, courseId, "approved"));
      const reject = document.createElement("button");
      reject.type = "button";
      reject.className = "text-button danger-button";
      reject.textContent = "拒绝";
      reject.addEventListener("click", () => reviewFile(file, courseId, "rejected"));
      actions.append(approve, reject);
    }
    actions.append(download);
    item.append(details, actions);
    fileList.append(item);
  });
  renderPagination(filePagination, data, (page) => loadCourseFiles(courseId, page));
}

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

async function editFile(file, courseId) {
  const title = window.prompt("请输入新的资料标题", file.title);
  if (title === null) return;
  const response = await fetch(`/api/files/${encodeURIComponent(file.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
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
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "text-button danger-button";
  remove.textContent = "删除课程";
  remove.addEventListener("click", () => removeCourse(course));
  courseActions.append(edit, remove);
}

async function editCourse(course) {
  const name = window.prompt("请输入新的课程名称", course.name);
  if (name === null) return;
  const response = await fetch(`/api/courses/${encodeURIComponent(course.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "课程更新失败。"));
    return;
  }
  currentCourse = await response.json();
  courseName.textContent = currentCourse.name;
  courseContext.textContent = courseContextText(currentCourse);
  renderCourseActions(currentCourse);
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
  const context = [course.college, course.semester].filter(Boolean).join(" · ");
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

function updateFileSelection() {
  const files = Array.from(fileInput.files || []);
  if (!files.length) {
    fileSelection.textContent = "单个文件不超过 20 兆字节。";
    fileSelection.className = "form-hint";
    return;
  }
  const total = files.reduce((sum, file) => sum + file.size, 0);
  const summary = `${files.length} 个文件 · 共 ${formatFileSize(total)}`;
  const oversized = files.filter((file) => file.size > MAX_FILE_SIZE);
  if (oversized.length) {
    fileSelection.textContent = `${summary}；${oversized
      .map((file) => file.name)
      .join("、")} 超过 20 兆字节`;
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
  const oversized = files.find((file) => file.size > MAX_FILE_SIZE);
  if (oversized) {
    setUploadMessage(`${oversized.name} 超过 20 兆字节。`, true);
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

async function loadUsers(page = 1) {
  if (!userList) return;
  currentUserPage = page;
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
  if (!users.length) {
    showState(userList, "没有匹配的用户");
    renderPagination(userPagination, null, () => {});
    return;
  }
  users.forEach((item) => userList.append(renderUserRow(item)));
  renderPagination(userPagination, data, (page) => loadUsers(page));
}

function renderUserRow(item) {
  const isSelf = item.id === currentUser?.id;
  const row = document.createElement("li");
  row.className = "user-row";

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
  row.append(identity, actions);
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
    body: JSON.stringify({ title }),
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
  previewClose?.addEventListener("click", closePreview);
  previewDialog?.querySelector("[data-preview-close]")?.addEventListener("click", closePreview);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closePreview();
  });
}

function initHomePage() {
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
  userFilterRole?.addEventListener("change", () => loadUsers(1));
  userFilterKeyword?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    loadUsers(1);
  });
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
  if (query || activeFilterCount()) searchFiles(query, 1);
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

async function bootstrap() {
  initAuth();
  await loadCurrentUser();
  if (courseList) initHomePage();
  if (fileList) await initCoursePage();
}

bootstrap();
