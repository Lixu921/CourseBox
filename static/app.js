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
const authStatus = document.querySelector("#auth-status");
const loginToggle = document.querySelector("#login-toggle");
const logoutButton = document.querySelector("#logout-button");
const loginPanel = document.querySelector("#login-panel");
const loginForm = document.querySelector("#login-form");
const loginMessage = document.querySelector("#login-message");
const adminCoursePanel = document.querySelector("#admin-course-panel");
const courseCreateForm = document.querySelector("#course-create-form");
const courseCreateMessage = document.querySelector("#course-create-message");

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ROLE_LABELS = { admin: "管理员", uploader: "上传者", viewer: "浏览者" };
const STATUS_LABELS = { approved: "已通过", pending: "待审核", rejected: "已拒绝" };
let currentUser = null;
let currentCourse = null;
let currentCourseId = null;
let currentFilePage = 1;

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

function formatUploadTime(value) {
  if (!value) return "上传时间未知";
  const date = new Date(`${value.replace(" ", "T")}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}

function courseUrl(course) {
  return `/course?id=${encodeURIComponent(course.id)}`;
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
  if (loginPanel && currentUser) loginPanel.hidden = true;
  if (adminCoursePanel) adminCoursePanel.hidden = currentUser?.role !== "admin";
  updateUploadAccess();
  if (currentCourse) renderCourseActions(currentCourse);
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
    title.textContent = file.title;
    const metadata = document.createElement("p");
    metadata.className = "course-meta";
    metadata.textContent = `${file.original_name} · ${formatFileSize(file.size)}`;
    const course = document.createElement("p");
    course.className = "result-course";
    course.textContent = `所属课程：${file.course.name}`;
    const actions = document.createElement("div");
    actions.className = "result-actions";
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

async function searchFiles(query, page = 1) {
  showState(courseList, "正在搜索资料...");
  courseHeading.textContent = "搜索结果";
  courseCount.textContent = "";
  coursePagination.innerHTML = "";
  setSearchLoading(true);
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&page=${page}&page_size=12`);
    if (!response.ok) throw new Error("搜索失败");
    renderSearchResults(await response.json());
  } catch (error) {
    showState(courseList, "搜索失败，请检查网络后重试。", true);
    courseCount.textContent = "";
  } finally {
    setSearchLoading(false);
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
    metadata.textContent = `${file.original_name} · ${formatFileSize(file.size)} · ${formatUploadTime(file.upload_time)}`;
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

function updateFileSelection() {
  const file = fileInput.files[0];
  if (!file) {
    fileSelection.textContent = "单个文件不超过 20 兆字节。";
    fileSelection.className = "form-hint";
    return;
  }
  fileSelection.textContent = `${file.name} · ${formatFileSize(file.size)}`;
  fileSelection.className = file.size > MAX_FILE_SIZE ? "form-hint error-message" : "form-hint";
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

function uploadFile(courseId, event) {
  event.preventDefault();
  uploadMessage.textContent = "";
  uploadMessage.className = "form-message";
  const selectedFile = fileInput.files[0];
  const title = document.querySelector("#file-title").value.trim();
  if (!title) {
    uploadMessage.textContent = "资料标题不能为空。";
    uploadMessage.className = "form-message error-message";
    return;
  }
  if (!selectedFile) {
    uploadMessage.textContent = "请选择要上传的文件。";
    uploadMessage.className = "form-message error-message";
    return;
  }
  if (selectedFile.size > MAX_FILE_SIZE) {
    uploadMessage.textContent = "文件不能超过 20 兆字节。";
    uploadMessage.className = "form-message error-message";
    return;
  }
  uploadButton.disabled = true;
  uploadButton.textContent = "上传中...";
  setUploadProgress(0, "准备上传");
  const request = new XMLHttpRequest();
  request.open("POST", `/api/courses/${encodeURIComponent(courseId)}/files`);
  request.upload.addEventListener("progress", (progressEvent) => {
    if (!progressEvent.lengthComputable) return;
    const value = Math.round((progressEvent.loaded / progressEvent.total) * 100);
    setUploadProgress(value, `已上传 ${value}%`);
  });
  request.addEventListener("load", async () => {
    let body = {};
    try {
      body = JSON.parse(request.responseText);
    } catch (error) {
      body = {};
    }
    if (request.status < 200 || request.status >= 300) {
      uploadMessage.textContent = body.error?.message || body.detail || "上传失败，请稍后重试。";
      uploadMessage.className = "form-message error-message";
      finishUpload();
      return;
    }
    uploadForm.reset();
    updateFileSelection();
    setUploadProgress(100, "上传完成");
    uploadMessage.textContent = currentUser?.role === "admin"
      ? "上传成功，资料已发布。"
      : "上传成功，资料正在等待管理员审核。";
    uploadMessage.className = "form-message success-message";
    await loadCourseFiles(courseId, 1);
    await refreshCourse();
    finishUpload(false);
  });
  request.addEventListener("error", () => {
    uploadMessage.textContent = "网络异常，上传失败，请稍后重试。";
    uploadMessage.className = "form-message error-message";
    finishUpload();
  });
  request.addEventListener("abort", () => {
    uploadMessage.textContent = "上传已取消。";
    uploadMessage.className = "form-message error-message";
    finishUpload();
  });
  request.addEventListener("timeout", () => {
    uploadMessage.textContent = "上传超时，请稍后重试。";
    uploadMessage.className = "form-message error-message";
    finishUpload();
  });
  request.timeout = 120000;
  request.send(new FormData(uploadForm));
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

function readError(response, fallback) {
  return response.json()
    .then((body) => body.error?.message || body.detail || fallback)
    .catch(() => fallback);
}

function initAuth() {
  loginToggle?.addEventListener("click", toggleLoginPanel);
  logoutButton?.addEventListener("click", logout);
  loginForm?.addEventListener("submit", submitLogin);
}

function initHomePage() {
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = searchInput.value.trim();
    if (query) {
      window.history.replaceState({}, "", `/?q=${encodeURIComponent(query)}`);
      searchFiles(query);
    } else {
      window.history.replaceState({}, "", "/");
      loadCourses();
    }
  });
  courseCreateForm?.addEventListener("submit", createCourse);
  const params = new URLSearchParams(window.location.search);
  const query = (params.get("q") || params.get("关键词"))?.trim();
  if (query) {
    searchInput.value = query;
    searchFiles(query);
  } else {
    loadCourses();
  }
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
  uploadForm.addEventListener("submit", (event) => uploadFile(currentCourseId, event));
  fileInput.addEventListener("change", updateFileSelection);
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
