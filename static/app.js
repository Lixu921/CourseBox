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

function courseUrl(course) {
  return `/课程?编号=${encodeURIComponent(course.id)}&名称=${encodeURIComponent(course.name)}`;
}

function renderPagination(container, data, onPage) {
  container.innerHTML = "";
  if (!data || data.total_pages <= 1) return;
  const previous = document.createElement("button");
  previous.type = "button";
  previous.textContent = "上一页";
  previous.disabled = data.page <= 1;
  previous.addEventListener("click", () => onPage(data.page - 1));
  const status = document.createElement("span");
  status.textContent = `${data.page} / ${data.total_pages}`;
  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "下一页";
  next.disabled = data.page >= data.total_pages;
  next.addEventListener("click", () => onPage(data.page + 1));
  container.append(previous, status, next);
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
    download.href = `/接口/资料/${encodeURIComponent(file.id)}/下载`;
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
    const response = await fetch(`/接口/课程?page=${page}&page_size=12`);
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
    const response = await fetch(`/接口/搜索?关键词=${encodeURIComponent(query)}&page=${page}&page_size=12`);
    if (!response.ok) throw new Error("搜索失败");
    renderSearchResults(await response.json());
  } catch (error) {
    showState(courseList, "搜索失败，请检查网络后重试。", true);
    courseCount.textContent = "";
  } finally {
    setSearchLoading(false);
  }
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
    const title = document.createElement("h3");
    title.textContent = file.title;
    const metadata = document.createElement("p");
    metadata.className = "file-meta";
    metadata.textContent = `${file.original_name} · ${formatFileSize(file.size)}`;
    details.append(title, metadata);

    const download = document.createElement("a");
    download.className = "download-link";
    download.href = `/接口/资料/${encodeURIComponent(file.id)}/下载`;
    download.textContent = "下载";
    download.setAttribute("download", "");

    const actions = document.createElement("div");
    actions.className = "file-actions";
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
    actions.append(edit, remove, download);
    item.append(details, actions);
    fileList.append(item);
  });
  renderPagination(filePagination, data, (page) => loadCourseFiles(courseId, page));
}

async function loadCourseFiles(courseId, page = 1) {
  showState(fileList, "正在加载资料...");
  filePagination.innerHTML = "";
  try {
    const response = await fetch(`/接口/课程/${encodeURIComponent(courseId)}/资料?page=${page}&page_size=12`);
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
  const response = await fetch(`/接口/资料/${encodeURIComponent(file.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "资料更新失败。"));
    return;
  }
  await loadCourseFiles(courseId);
}

async function removeFile(file, courseId) {
  if (!window.confirm(`确定删除“${file.title}”吗？`)) return;
  const response = await fetch(`/接口/资料/${encodeURIComponent(file.id)}`, { method: "DELETE" });
  if (!response.ok) {
    window.alert(await readError(response, "资料删除失败。"));
    return;
  }
  await loadCourseFiles(courseId);
}

function renderCourseActions(course) {
  courseActions.hidden = false;
  courseActions.innerHTML = "";
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
  const response = await fetch(`/接口/课程/${encodeURIComponent(course.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    window.alert(await readError(response, "课程更新失败。"));
    return;
  }
  const updated = await response.json();
  courseName.textContent = updated.name;
  const params = new URLSearchParams(window.location.search);
  params.set("名称", updated.name);
  window.history.replaceState({}, "", `/课程?${params}`);
  renderCourseActions(updated);
}

async function removeCourse(course) {
  if (!window.confirm(`确定删除“${course.name}”及其全部资料吗？`)) return;
  const response = await fetch(`/接口/课程/${encodeURIComponent(course.id)}`, { method: "DELETE" });
  if (!response.ok) {
    window.alert(await readError(response, "课程删除失败。"));
    return;
  }
  window.location.href = "/";
}

function readError(response, fallback) {
  return response.json()
    .then((body) => body.detail || fallback)
    .catch(() => fallback);
}

async function uploadFile(courseId, event) {
  event.preventDefault();
  uploadMessage.textContent = "";
  uploadMessage.className = "form-message";
  uploadButton.disabled = true;
  uploadButton.textContent = "上传中...";

  try {
    const response = await fetch(`/接口/课程/${encodeURIComponent(courseId)}/资料`, {
      method: "POST",
      body: new FormData(uploadForm),
    });
    if (!response.ok) throw new Error(await readError(response, "上传失败，请稍后重试。"));
    uploadForm.reset();
    uploadMessage.textContent = "上传成功，资料列表已更新。";
    uploadMessage.className = "form-message success-message";
    await loadCourseFiles(courseId);
  } catch (error) {
    uploadMessage.textContent = error.message || "上传失败，请稍后重试。";
    uploadMessage.className = "form-message error-message";
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = "上传资料";
  }
}

function initHomePage() {
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = searchInput.value.trim();
    if (query) {
      window.history.replaceState({}, "", `/?关键词=${encodeURIComponent(query)}`);
      searchFiles(query);
    } else {
      window.history.replaceState({}, "", "/");
      loadCourses();
    }
  });

  const params = new URLSearchParams(window.location.search);
  const query = params.get("关键词")?.trim();
  if (query) {
    searchInput.value = query;
    searchFiles(query);
  } else {
    loadCourses();
  }
}

function initCoursePage() {
  const params = new URLSearchParams(window.location.search);
  const courseId = params.get("编号");
  courseName.textContent = "正在加载课程...";
  courseContext.textContent = courseId ? "课程资料共享" : "缺少课程信息";
  if (!courseId || !/^\d+$/.test(courseId)) {
    showState(fileList, "无法识别这门课程，请从首页重新进入。", true);
    uploadForm.hidden = true;
    return;
  }

  uploadForm.addEventListener("submit", (event) => uploadFile(courseId, event));
  fetch(`/接口/课程/${encodeURIComponent(courseId)}`)
    .then((response) => {
      if (!response.ok) throw new Error("课程不存在");
      return response.json();
    })
    .then((course) => {
      courseName.textContent = course.name;
      courseContext.textContent = `${course.college || ""}${course.college && course.semester ? " · " : ""}${course.semester || ""} · ${course.file_count} 份资料`;
      renderCourseActions(course);
      return loadCourseFiles(courseId);
    })
    .catch((error) => {
      courseName.textContent = "课程不存在";
      courseContext.textContent = error.message;
      uploadForm.hidden = true;
    });
}

if (courseList) initHomePage();
if (fileList) initCoursePage();
