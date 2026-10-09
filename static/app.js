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
const passwordToggle = document.querySelector("#password-toggle");
const passwordPanel = document.querySelector("#password-panel");
const passwordForm = document.querySelector("#password-form");
const passwordMessage = document.querySelector("#password-message");
const logoutButton = document.querySelector("#logout-button");
const loginPanel = document.querySelector("#login-panel");
const authHint = document.querySelector("#auth-hint");
const authHintLogin = document.querySelector("#auth-hint-login");
const loginForm = document.querySelector("#login-form");
const loginMessage = document.querySelector("#login-message");
const registerToggle = document.querySelector("#register-toggle");
const registerPanel = document.querySelector("#register-panel");
const registerForm = document.querySelector("#register-form");
const registerMessage = document.querySelector("#register-message");
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
const exportFilesButton = document.querySelector("#export-files");
const exportAuditButton = document.querySelector("#export-audit");
const exportMessage = document.querySelector("#export-message");
const trashPanel = document.querySelector("#trash-panel");
const trashList = document.querySelector("#trash-list");
const trashPagination = document.querySelector("#trash-pagination");
const trashFilterKeyword = document.querySelector("#trash-filter-keyword");
const trashFilterButton = document.querySelector("#trash-filter-button");
const trashSelectAll = document.querySelector("#trash-select-all");
const trashSelectionCount = document.querySelector("#trash-selection-count");
const trashBatchRestore = document.querySelector("#trash-batch-restore");
const trashBatchPurge = document.querySelector("#trash-batch-purge");
const trashBatchMessage = document.querySelector("#trash-batch-message");
const searchCourse = document.querySelector("#search-course");
const searchType = document.querySelector("#search-type");
const searchStart = document.querySelector("#search-start");
const searchEnd = document.querySelector("#search-end");
const searchSort = document.querySelector("#search-sort");
const searchResetButton = document.querySelector("#search-reset");
const overviewPanel = document.querySelector("#overview-panel");
const overviewList = document.querySelector("#overview-list");
const sessionsPanel = document.querySelector("#sessions-panel");
const sessionsList = document.querySelector("#sessions-list");
const hotList = document.querySelector("#hot-list");
const recentList = document.querySelector("#recent-list");
const commentDialog = document.querySelector("#comment-dialog");
const commentTitle = document.querySelector("#comment-title");
const commentList = document.querySelector("#comment-list");
const commentForm = document.querySelector("#comment-form");
const commentInput = document.querySelector("#comment-input");
const commentMessage = document.querySelector("#comment-message");
const commentHint = document.querySelector("#comment-hint");
const commentClose = document.querySelector("#comment-close");
// 评论弹层当前针对的资料编号，以及轮询定时器（非实时，用轮询刷新）。
let commentFileId = null;
let commentTimer = null;

// 上传大小上限：默认 20 MB，登录后在课程页用后端配额里的 max_file_size 覆盖。
// 不写死，避免管理员调过 COURSEBOX_MAX_FILE_SIZE 后前后端判断不一致。
let maxFileSize = 20 * 1024 * 1024;
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
// 回收站里被勾选的资料编号，同样只在当前这一页有效。
const selectedTrashIds = new Set();
let currentTrashIds = [];

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
  if (registerToggle) registerToggle.hidden = Boolean(currentUser);
  if (passwordToggle) passwordToggle.hidden = !currentUser;
  logoutButton.hidden = !currentUser;
  if (authHint) authHint.hidden = Boolean(currentUser);
  if (loginPanel && currentUser) loginPanel.hidden = true;
  if (registerPanel && currentUser) registerPanel.hidden = true;
  // 退出登录后必须收起改密码面板，否则下一个访客能看到空表单。
  if (passwordPanel && !currentUser) passwordPanel.hidden = true;
  if (adminCoursePanel) adminCoursePanel.hidden = currentUser?.role !== "admin";
  if (adminUserPanel) adminUserPanel.hidden = currentUser?.role !== "admin";
  if (auditPanel) auditPanel.hidden = currentUser?.role !== "admin";
  if (trashPanel) trashPanel.hidden = currentUser?.role !== "admin";
  if (overviewPanel) overviewPanel.hidden = currentUser?.role !== "admin";
  if (sessionsPanel) sessionsPanel.hidden = !currentUser;
  if (myUploadsPanel) myUploadsPanel.hidden = !currentUser;
  updateUploadAccess();
  if (currentCourse) renderCourseActions(currentCourse);
  // 登录/登出会改变「批量审核」按钮该不该出现，重新同步一次勾选状态。
  syncFileSelection();
  ensureUserPanelLoaded();
  ensureAuditLoaded();
  ensureTrashLoaded();
  ensureOverviewLoaded();
  ensureSessionsLoaded();
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

function ensureOverviewLoaded() {
  if (!overviewPanel || currentUser?.role !== "admin") return;
  if (overviewPanel.dataset.loaded === "1") return;
  overviewPanel.dataset.loaded = "1";
  loadOverview();
}

function ensureSessionsLoaded() {
  if (!sessionsPanel || !currentUser) return;
  if (sessionsPanel.dataset.loaded === "1") return;
  sessionsPanel.dataset.loaded = "1";
  loadSessions();
}

// 切换账户时必须丢掉上一个账户的加载标记，否则会沿用旧列表。
function resetPanelLoadFlags() {
  adminUserPanel?.removeAttribute("data-loaded");
  auditPanel?.removeAttribute("data-loaded");
  trashPanel?.removeAttribute("data-loaded");
  overviewPanel?.removeAttribute("data-loaded");
  sessionsPanel?.removeAttribute("data-loaded");
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
  if (!loginPanel.hidden) {
    if (registerPanel) registerPanel.hidden = true;
    document.querySelector("#login-username")?.focus();
  }
}

function toggleRegisterPanel() {
  if (!registerPanel) return;
  registerPanel.hidden = !registerPanel.hidden;
  if (!registerPanel.hidden) {
    if (loginPanel) loginPanel.hidden = true;
    registerMessage.textContent = "";
    registerMessage.className = "form-message";
    document.querySelector("#register-username")?.focus();
  }
}

async function submitRegister(event) {
  event.preventDefault();
  registerMessage.textContent = "正在注册...";
  registerMessage.className = "form-message";
  const submitButton = registerForm.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const response = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(registerForm))),
    });
    if (!response.ok) throw new Error(await readError(response, "注册失败。"));
    registerForm.reset();
    registerPanel.hidden = true;
    // 注册成功即已登录，直接刷新登录态。
    currentUser = await response.json();
    resetPanelLoadFlags();
    updateAuthUI();
  } catch (error) {
    registerMessage.textContent = error.message || "注册失败，请稍后重试。";
    registerMessage.className = "form-message error-message";
  } finally {
    submitButton.disabled = false;
  }
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

function togglePasswordPanel() {
  if (!passwordPanel) return;
  passwordPanel.hidden = !passwordPanel.hidden;
  if (passwordPanel.hidden) return;
  // 每次打开都清空上一次的输入与提示，别把密码留在 DOM 里。
  passwordForm?.reset();
  setPasswordMessage("");
  document.querySelector("#password-current")?.focus();
}

function setPasswordMessage(message, state = "info") {
  if (!passwordMessage) return;
  passwordMessage.textContent = message;
  const classes = {
    error: "form-message error-message",
    success: "form-message success-message",
  };
  passwordMessage.className = classes[state] || "form-message";
}

async function submitPasswordChange(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(passwordForm));
  // 两次输入不一致在本地就能发现，不必浪费一次请求（也不会把密码发出去两次）。
  if (data.new_password !== data.confirm_password) {
    setPasswordMessage("两次输入的新密码不一致。", "error");
    return;
  }
  const submitButton = passwordForm.querySelector("button[type=submit]");
  submitButton.disabled = true;
  setPasswordMessage("正在保存...");
  try {
    const response = await fetch("/api/me/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: data.current_password,
        new_password: data.new_password,
      }),
    });
    if (!response.ok) throw new Error(await readError(response, "修改密码失败。"));
    passwordForm.reset();
    setPasswordMessage("密码已更新，其它设备上的登录已被退出。", "success");
  } catch (error) {
    setPasswordMessage(error.message || "修改密码失败。", "error");
  } finally {
    submitButton.disabled = false;
  }
}

function matchesQuery(value, query) {
  const terms = (query || "")
    .split(/\s+/)
    .map((term) => term.trim().toLowerCase())
    .filter(Boolean);
  if (!terms.length) return false;
  const text = String(value ?? "").toLowerCase();
  return terms.some((term) => text.includes(term));
}

// 「命中：…」提示。回答的是「这条结果为什么出现」——被检索的字段在卡片上都已经
// 完整显示，所以这里只报字段名，不再重复抄一遍内容。
function matchHint(labels) {
  if (!labels.length) return null;
  const hint = document.createElement("p");
  hint.className = "match-hint";
  hint.textContent = `命中：${labels.join("、")}`;
  return hint;
}

function courseCard(course, query) {
  const card = document.createElement("a");
  card.className = "course-card";
  card.href = courseUrl(course);
  const title = document.createElement("h3");
  title.append(highlight(course.name, query));
  card.append(title);
  if (course.college) {
    const college = document.createElement("p");
    college.className = "course-meta";
    college.append(highlight(course.college, query));
    card.append(college);
  }
  if (course.tags && course.tags.length) {
    const tagRow = document.createElement("p");
    tagRow.className = "course-tags";
    course.tags.forEach((tag) => {
      const chip = document.createElement("span");
      chip.className = "tag-chip";
      chip.append(highlight(tag, query));
      tagRow.append(chip);
    });
    card.append(tagRow);
  }
  // 课程是按 课程名 / 学院 / 标签 OR 匹配的，所以必须说清是哪个命中的：
  // 否则搜「计算机」时用户只看到课程名，完全不知道它为什么被搜出来。
  const labels = [];
  if (matchesQuery(course.name, query)) labels.push("课程名");
  if (matchesQuery(course.college, query)) labels.push("学院");
  if (matchesQuery((course.tags || []).join(" "), query)) labels.push("标签");
  if (matchesQuery((course.tags || []).join(" "), query)) labels.push("标签");
  const hint = matchHint(labels);
  if (hint) card.append(hint);
  return card;
}

function courseGrid(courses, query = "") {
  const grid = document.createElement("div");
  grid.className = "course-grid";
  courses.forEach((course) => grid.append(courseCard(course, query)));
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
  // 搜索对上传者也会返回自己的待审资料，标出状态，避免与已通过的混淆。
  if (file.status && file.status !== "approved") {
    title.append(statusBadge(file.status));
  }
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
  // matched_fields 由后端算好（标题 / 文件名 / 课程名），这里只负责展示。
  const hint = matchHint(file.matched_fields || []);
  card.append(title, metadata, course);
  if (hint) card.append(hint);
  card.append(actions);
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
    if (courses.length) courseList.append(courseGrid(courses, query));
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
  // 后端上限才是权威值，用它覆盖前端的默认上限与提示文案。
  if (quota.max_file_size) maxFileSize = quota.max_file_size;
  if (fileSelection && fileInput && !(fileInput.files || []).length) {
    fileSelection.textContent = fileSelectionHint();
  }
  const parts = [`本次最多可上传 ${formatFileSize(quota.allowed_bytes)}`];
  if (quota.course_remaining != null) {
    parts.push(`本课程剩余 ${formatFileSize(quota.course_remaining)}`);
  }
  if (quota.site_remaining != null) {
    parts.push(`全站剩余 ${formatFileSize(quota.site_remaining)}`);
  }
  if (quota.user_remaining != null) {
    parts.push(`我的上传剩余 ${formatFileSize(quota.user_remaining)}`);
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
    metadata.textContent = `${file.original_name} · ${formatFileSize(file.size)} · ${formatDateTime(file.upload_time) || "上传时间未知"} · 下载 ${file.download_count || 0} 次`;
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
    const comment = document.createElement("button");
    comment.type = "button";
    comment.className = "text-button";
    comment.textContent = `评论 ${file.comment_count || 0}`;
    comment.addEventListener("click", () => openComments(file));
    actions.append(comment);
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

