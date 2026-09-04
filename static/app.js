const courseList = document.querySelector("#course-list");
const courseCount = document.querySelector("#course-count");
const courseHeading = document.querySelector("#course-heading");
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#search-input");
const searchButton = searchForm?.querySelector("button");
const courseName = document.querySelector("#course-name");
const courseContext = document.querySelector("#course-context");
const fileList = document.querySelector("#file-list");
const fileCount = document.querySelector("#file-count");
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

function renderCourses(courses) {
  courseList.innerHTML = "";
  courseHeading.textContent = "全部课程";
  courseCount.textContent = `${courses.length} 门`;
  if (!courses.length) {
    showState(courseList, "还没有课程资料");
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
}

function renderSearchResults(results) {
  courseList.innerHTML = "";
  courseHeading.textContent = "搜索结果";
  courseCount.textContent = `${results.length} 份`;
  if (!results.length) {
    showState(courseList, "没有找到相关资料");
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
}

function setSearchLoading(isLoading) {
  searchButton.disabled = isLoading;
  searchButton.textContent = isLoading ? "搜索中..." : "搜索";
}

async function loadCourses() {
  showState(courseList, "正在加载课程...");
  courseCount.textContent = "";
  try {
    const response = await fetch("/接口/课程");
    if (!response.ok) throw new Error("课程加载失败");
    renderCourses(await response.json());
  } catch (error) {
    showState(courseList, "课程加载失败，请稍后重试。", true);
    courseHeading.textContent = "全部课程";
    courseCount.textContent = "";
  }
}

async function searchFiles(query) {
  showState(courseList, "正在搜索资料...");
  courseHeading.textContent = "搜索结果";
  courseCount.textContent = "";
  setSearchLoading(true);
  try {
    const response = await fetch(`/接口/搜索?关键词=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error("搜索失败");
    renderSearchResults(await response.json());
  } catch (error) {
    showState(courseList, "搜索失败，请检查网络后重试。", true);
    courseCount.textContent = "";
  } finally {
    setSearchLoading(false);
  }
}

function renderFiles(files) {
  fileList.innerHTML = "";
  fileCount.textContent = `${files.length} 份`;
  if (!files.length) {
    showState(fileList, "这个课程还没有资料，上传第一份吧。");
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

    item.append(details, download);
    fileList.append(item);
  });
}

async function loadCourseFiles(courseId) {
  showState(fileList, "正在加载资料...");
  try {
    const response = await fetch(`/接口/课程/${encodeURIComponent(courseId)}/资料`);
    if (!response.ok) {
      if (response.status === 404) throw new Error("课程不存在");
      throw new Error("资料加载失败");
    }
    renderFiles(await response.json());
  } catch (error) {
    showState(fileList, `${error.message}，请返回课程列表重试。`, true);
    fileCount.textContent = "";
  }
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
  const name = params.get("名称");

  courseName.textContent = name || "课程资料";
  courseContext.textContent = courseId ? "课程资料共享" : "缺少课程信息";
  if (!courseId || !/^\d+$/.test(courseId)) {
    showState(fileList, "无法识别这门课程，请从首页重新进入。", true);
    uploadForm.hidden = true;
    return;
  }

  uploadForm.addEventListener("submit", (event) => uploadFile(courseId, event));
  loadCourseFiles(courseId);
}

if (courseList) initHomePage();
if (fileList) initCoursePage();
