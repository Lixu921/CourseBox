const courseList = document.querySelector("#course-list");
const courseCount = document.querySelector("#course-count");
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#search-input");

function showState(message, isError = false) {
  courseList.innerHTML = "";
  const element = document.createElement("p");
  element.className = isError ? "state-message error-message" : "state-message";
  element.textContent = message;
  courseList.append(element);
  courseCount.textContent = "";
}

function renderCourses(courses) {
  courseList.innerHTML = "";
  courseCount.textContent = `${courses.length} 门`;
  if (!courses.length) {
    showState("还没有课程资料");
    return;
  }

  courses.forEach((course) => {
    const card = document.createElement("a");
    card.className = "course-card";
    card.href = `course.html?id=${encodeURIComponent(course.id)}&name=${encodeURIComponent(course.name)}`;
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

async function loadCourses() {
  showState("正在加载课程...");
  try {
    const response = await fetch("/api/courses");
    if (!response.ok) throw new Error("课程加载失败");
    renderCourses(await response.json());
  } catch (error) {
    showState("课程加载失败，请稍后重试。", true);
  }
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = searchInput.value.trim();
  if (query) window.location.href = `course.html?q=${encodeURIComponent(query)}`;
});

loadCourses();
