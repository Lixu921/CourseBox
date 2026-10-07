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
const fileToolbar = document.querySelector("#file-toolbar");
const fileSelectAll = document.querySelector("#file-select-all");
const fileSelectionCount = document.querySelector("#file-selection-count");
const archiveSelectedButton = document.querySelector("#archive-selected");
const archiveAllButton = document.querySelector("#archive-all");
const batchApproveButton = document.querySelector("#batch-approve");
const batchRejectButton = document.querySelector("#batch-reject");
const courseActions = document.querySelector("#course-actions");
const uploadForm = document.querySelector("#upload-form");
const uploadButton = document.querySelector("#upload-button");
const uploadMessage = document.querySelector("#upload-message");
const uploadAccessNote = document.querySelector("#upload-access-note");
const uploadQuota = document.querySelector("#upload-quota");
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
const userBatchToolbar = document.querySelector("#user-batch-toolbar");
const userSelectAll = document.querySelector("#user-select-all");
const userSelectionCount = document.querySelector("#user-selection-count");
const userBatchEnable = document.querySelector("#user-batch-enable");
const userBatchDisable = document.querySelector("#user-batch-disable");
const userBatchRole = document.querySelector("#user-batch-role");
const userBatchRoleApply = document.querySelector("#user-batch-role-apply");
const userBatchMessage = document.querySelector("#user-batch-message");
const myUploadsPanel = document.querySelector("#my-uploads-panel");
const myUploadsList = document.querySelector("#my-uploads-list");
const myUploadsCount = document.querySelector("#my-uploads-count");
const myUploadsPagination = document.querySelector("#my-uploads-pagination");
const myUploadsStatus = document.querySelector("#my-uploads-status");
const myUploadsRefreshButton = document.querySelector("#my-uploads-refresh");
const auditPanel = document.querySelector("#audit-panel");
const auditList = document.querySelector("#audit-list");
const auditPagination = document.querySelector("#audit-pagination");
const auditFilterKeyword = document.querySelector("#audit-filter-keyword");
const auditFilterAction = document.querySelector("#audit-filter-action");
const auditFilterEntity = document.querySelector("#audit-filter-entity");
const auditFilterButton = document.querySelector("#audit-filter-button");
const trashPanel = document.querySelector("#trash-panel");
const trashList = document.querySelector("#trash-list");
const trashPagination = document.querySelector("#trash-pagination");
const trashFilterKeyword = document.querySelector("#trash-filter-keyword");
const trashFilterButton = document.querySelector("#trash-filter-button");
const searchCourse = document.querySelector("#search-course");
const searchType = document.querySelector("#search-type");
const searchStart = document.querySelector("#search-start");
const searchEnd = document.querySelector("#search-end");
const searchSort = document.querySelector("#search-sort");
const searchResetButton = document.querySelector("#search-reset");

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ROLE_LABELS = { admin: "管理员", uploader: "上传者", viewer: "浏览者" };
const STATUS_LABELS = { approved: "已通过", pending: "待审核", rejected: "已拒绝" };
// 操作记录里 action / entity_type 的取值来自后端白名单，这里只做展示用翻译。
const AUDIT_ACTION_LABELS = {
  create: "新建",
  update: "修改",
  delete: "删除",
  download: "下载",
  preview: "预览",
  login: "登录",
  logout: "退出登录",
  reset_password: "重置密码",
  restore: "从回收站恢复",
  purge: "彻底删除",
  approved: "审核通过",
  rejected: "审核拒绝",
};
const AUDIT_ENTITY_LABELS = { course: "课程", file: "资料", user: "用户" };
// 与后端 PREVIEW_MEDIA_TYPES 保持一致，只预览确定不会执行脚本的类型。
const PREVIEW_IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif"]);
const PREVIEW_DOCUMENT_EXTENSIONS = new Set(["pdf", "txt", "md"]);
let currentUser = null;
let currentCourse = null;
let currentCourseId = null;
let currentFilePage = 1;
let currentUserPage = 1;
let currentAuditPage = 1;
let currentTrashPage = 1;
let currentMyUploadPage = 1;
let currentSearchQuery = "";
// 课程页里被勾选、准备打包下载的资料编号，以及当前这一页的资料编号。
const selectedFileIds = new Set();
let currentFileIds = [];
// 用户管理里被勾选的用户编号。翻页时清空，避免误操作到看不见的行。
const selectedUserIds = new Set();
let currentUserIds = [];

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
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} 兆字节`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} 吉字节`;
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
  if (auditPanel) auditPanel.hidden = currentUser?.role !== "admin";
  if (trashPanel) trashPanel.hidden = currentUser?.role !== "admin";
  if (myUploadsPanel) myUploadsPanel.hidden = !currentUser;
  updateUploadAccess();
  if (currentCourse) renderCourseActions(currentCourse);
  // 登录/登出会改变「批量审核」按钮该不该出现，重新同步一次勾选状态。
  syncFileSelection();
  ensureUserPanelLoaded();
  ensureAuditLoaded();
  ensureTrashLoaded();
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

function ensureAuditLoaded() {
  if (!auditPanel || currentUser?.role !== "admin") return;
  if (auditPanel.dataset.loaded === "1") return;
  auditPanel.dataset.loaded = "1";
  loadAudit(1);
}

function ensureTrashLoaded() {
  if (!trashPanel || currentUser?.role !== "admin") return;
  if (trashPanel.dataset.loaded === "1") return;
  trashPanel.dataset.loaded = "1";
  loadTrash(1);
}

// 切换账户时必须丢掉上一个账户的加载标记，否则会沿用旧列表。
function resetPanelLoadFlags() {
  adminUserPanel?.removeAttribute("data-loaded");
  auditPanel?.removeAttribute("data-loaded");
  trashPanel?.removeAttribute("data-loaded");
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

function courseCard(course) {
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
  return card;
}

function courseGrid(courses) {
  const grid = document.createElement("div");
  grid.className = "course-grid";
  courses.forEach((course) => grid.append(courseCard(course)));
  return grid;
}

function groupHeading(text) {
  const heading = document.createElement("h3");
  heading.className = "result-group-heading";
  heading.textContent = text;
  return heading;
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
  courseList.append(courseGrid(courses));
  renderPagination(coursePagination, data, (page) => loadCourses(page));
}

function searchResultCard(file, query) {
  const card = document.createElement("article");
  card.className = "search-result-card";
  const title = document.createElement("h3");
  title.append(highlight(file.title, query));
  const metadata = document.createElement("p");
  metadata.className = "course-meta";
  metadata.append(highlight(file.original_name, query));
  metadata.append(` · ${formatFileSize(file.size)}`);
  const course = document.createElement("p");
  course.className = "result-course";
  course.append("所属课程：");
  course.append(highlight(file.course.name, query));
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
  return card;
}

// 合并搜索：同一个关键词同时找课程和资料，分两组展示。
// 只勾了筛选条件（没有关键词）时退化成「筛选资料」。
function renderCombinedSearch(coursesData, filesData, page) {
  const courses = coursesData?.items || [];
  const files = filesData.items || [];
  const query = currentSearchQuery;
  courseList.innerHTML = "";
  courseHeading.textContent = query ? "搜索结果" : "筛选结果";

  const parts = [];
  if (coursesData) parts.push(`课程 ${coursesData.total} 门`);
  parts.push(`资料 ${filesData.total} 份`);
  courseCount.textContent = parts.join(" · ");

  if (!courses.length && !files.length) {
    showState(courseList, query ? "没有找到匹配的课程或资料" : "没有找到匹配的资料");
    renderPagination(coursePagination, null, () => {});
    return;
  }

  if (coursesData) {
    courseList.append(groupHeading(`课程（${coursesData.total} 门）`));
    if (courses.length) courseList.append(courseGrid(courses));
    else courseList.append(stateLine("没有匹配的课程"));
  }

  courseList.append(groupHeading(`资料（${filesData.total} 份）`));
  if (files.length) {
    files.forEach((file) => courseList.append(searchResultCard(file, query)));
    // 分页跟着「资料」这组走：课程一组是一次性展示的前 12 门。
    renderPagination(coursePagination, filesData, (next) => runCombinedSearch(next));
  } else {
    courseList.append(stateLine("没有匹配的资料"));
    renderPagination(coursePagination, null, () => {});
  }
}

function stateLine(message) {
  const element = document.createElement("p");
  element.className = "state-message";
  element.textContent = message;
  return element;
}

function setSearchLoading(isLoading) {
  searchButton.disabled = isLoading;
  searchButton.textContent = isLoading ? "搜索中..." : "搜索";
}

async function loadCourses(page = 1) {
  showState(courseList, "正在加载课程...");
  courseCount.textContent = "";
  coursePagination.innerHTML = "";
  const params = new URLSearchParams({ page: String(page), page_size: "12" });
  try {
    const response = await fetch(`/api/courses?${params}`);
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

async function runCombinedSearch(page = 1) {
  const query = searchInput.value.trim();
  currentSearchQuery = query;
  showState(courseList, "正在搜索...");
  courseHeading.textContent = query ? "搜索结果" : "筛选结果";
  courseCount.textContent = "";
  coursePagination.innerHTML = "";
  setSearchLoading(true);
  try {
    const params = searchFilterParams();
    params.set("q", query);
    params.set("page", String(page));
    params.set("page_size", "12");
    const requests = [fetch(`/api/search?${params}`)];
    // 没有关键词时只筛资料：拿课程去匹配空关键词没有意义。
    if (query) {
      const courseParams = new URLSearchParams({
        page: "1",
        page_size: "12",
        关键词: query,
      });
      requests.push(fetch(`/api/courses?${courseParams}`));
    }
    const [filesResponse, coursesResponse] = await Promise.all(requests);
    if (!filesResponse.ok) throw new Error(await readError(filesResponse, "搜索失败"));
    const filesData = await filesResponse.json();
    const coursesData = coursesResponse?.ok ? await coursesResponse.json() : null;
    renderCombinedSearch(coursesData, filesData, page);
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
  if (query || activeFilterCount()) runCombinedSearch(1);
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
  loadCourseQuota();
}

async function loadCourseQuota() {
  if (!uploadQuota || !currentCourseId) return;
  const canUpload = currentUser && ["admin", "uploader"].includes(currentUser.role);
  if (!canUpload) {
    uploadQuota.hidden = true;
    return;
  }
  try {
    const response = await fetch(
      `/api/courses/${encodeURIComponent(currentCourseId)}/quota`
    );
    if (!response.ok) throw new Error(await readError(response, "剩余容量获取失败。"));
    renderCourseQuota(await response.json());
  } catch (error) {
    uploadQuota.textContent = error.message || "剩余容量获取失败。";
    uploadQuota.hidden = false;
  }
}

function renderCourseQuota(quota) {
  if (!uploadQuota) return;
  const parts = [`本次最多可上传 ${formatFileSize(quota.allowed_bytes)}`];
  if (quota.course_remaining != null) {
    parts.push(`本课程剩余 ${formatFileSize(quota.course_remaining)}`);
  }
  if (quota.site_remaining != null) {
    parts.push(`全站剩余 ${formatFileSize(quota.site_remaining)}`);
  }
  uploadQuota.textContent = `${parts.join(" · ")}（当前限制：${quota.reason}）`;
  uploadQuota.hidden = false;
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
  currentFileIds = files.map((file) => file.id);
  if (fileToolbar) fileToolbar.hidden = !files.length;
  if (!files.length) {
    showState(fileList, "这个课程还没有资料，上传第一份吧。");
    renderPagination(filePagination, null, () => {});
    syncFileSelection();
    return;
  }
  files.forEach((file) => {
    const item = document.createElement("li");
    item.className = "file-row";
    const select = document.createElement("input");
    select.type = "checkbox";
    select.className = "file-select";
    select.checked = selectedFileIds.has(file.id);
    select.setAttribute("aria-label", `选择「${file.title}」`);
    select.addEventListener("change", () => {
      if (select.checked) selectedFileIds.add(file.id);
      else selectedFileIds.delete(file.id);
      syncFileSelection();
    });
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
    item.append(select, details, actions);
    fileList.append(item);
  });
  syncFileSelection();
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

function initArchiveControls() {
  if (!fileToolbar) return;
  archiveSelectedButton?.addEventListener("click", () => {
    if (selectedFileIds.size) downloadArchive([...selectedFileIds]);
  });
  archiveAllButton?.addEventListener("click", () => downloadArchive([]));
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
    method: "PATCH",
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
  const params = new URLSearchParams({ page: String(page), page_size: "10" });
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
  showState(trashList, "正在加载回收站...");
  trashPagination.innerHTML = "";
  try {
    const response = await fetch(`/api/trash?${trashQuery(page)}`);
    if (!response.ok) throw new Error(await readError(response, "回收站加载失败。"));
    renderTrash(await response.json());
  } catch (error) {
    showState(trashList, error.message || "回收站加载失败。", true);
    trashPagination.innerHTML = "";
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
  if (!records.length) {
    showState(trashList, "回收站是空的");
    renderPagination(trashPagination, null, () => {});
    return;
  }
  records.forEach((item) => trashList.append(renderTrashRow(item)));
  renderPagination(trashPagination, data, (page) => loadTrash(page));
}

function renderTrashRow(item) {
  const row = document.createElement("li");
  row.className = "user-row";

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
  row.append(identity, actions);
  return row;
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

async function bootstrap() {
  initAuth();
  await loadCurrentUser();
  if (courseList) initHomePage();
  if (fileList) await initCoursePage();
}

bootstrap();
