// State
let currentDate = new Date(); // The date currently being viewed for "Today's Card"
let currentMonthDate = new Date(); // The month being viewed in Calendar

document.addEventListener('DOMContentLoaded', () => {
    updateDateDisplay();
    const dateStr = formatDateRequest(currentDate);
    fetchStats(dateStr);
    fetchSessions(dateStr);

    fetchMonthStats(currentDate.getFullYear(), currentDate.getMonth() + 1);

    // Event Listeners
    document.getElementById('prev-day').addEventListener('click', () => changeDate(-1));
    document.getElementById('next-day').addEventListener('click', () => changeDate(1));
});

function formatDateRequest(date) {
    const y = date.getFullYear();
    const m = (date.getMonth() + 1).toString().padStart(2, '0');
    const d = date.getDate().toString().padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function updateDateDisplay() {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('current-date-display').textContent = currentDate.toLocaleDateString('zh-CN', options);

    // Check if currentDate is today to disable "Next" arrow
    const today = new Date();
    const isToday = currentDate.toDateString() === today.toDateString();

    const nextBtn = document.getElementById('next-day');
    if (isToday) {
        nextBtn.classList.add('disabled');
    } else {
        nextBtn.classList.remove('disabled');
    }
}

function changeDate(delta) {
    const today = new Date();
    const newDate = new Date(currentDate);
    newDate.setDate(newDate.getDate() + delta);

    // Prevent going to future
    if (newDate > today) return;

    currentDate = newDate;
    updateDateDisplay();

    const dateStr = formatDateRequest(currentDate);
    fetchStats(dateStr);
    fetchSessions(dateStr);

    // Reload calendar if month changed?
    if (currentDate.getMonth() !== currentMonthDate.getMonth()) {
        currentMonthDate = new Date(currentDate);
        fetchMonthStats(currentDate.getFullYear(), currentDate.getMonth() + 1);
    }
}

async function fetchStats(dateStr) {
    try {
        const response = await fetch(`/api/stats?date=${dateStr}`);
        const data = await response.json();

        document.getElementById('today-duration').textContent = `${(data.today_duration / 60).toFixed(1)} min`;
        document.getElementById('today-keystrokes').textContent = data.today_keystrokes.toLocaleString();
        document.getElementById('today-efficiency').textContent = `${Math.round(data.today_efficiency * 100)}%`;
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

async function fetchSessions(dateStr) {
    try {
        let url = '/api/sessions';
        if (dateStr) {
            url += `?date=${dateStr}`;
        }
        const response = await fetch(url);
        const sessions = await response.json();

        const container = document.getElementById('session-list');
        container.innerHTML = '';

        const template = document.getElementById('session-card-template');

        sessions.forEach(session => {
            const clone = document.importNode(template.content, true);
            const card = clone.querySelector('.session-card');

            const dateObj = new Date(session.date);
            clone.querySelector('.session-date').textContent = dateObj.toLocaleDateString();
            clone.querySelector('.session-time').textContent = dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            clone.querySelector('.session-total-duration').textContent = formatDuration(session.total_duration);
            clone.querySelector('.session-active-duration').textContent = formatDuration(session.active_duration);
            clone.querySelector('.session-keystrokes').textContent = session.keystrokes.toLocaleString();
            clone.querySelector('.session-efficiency').textContent = `${Math.round(session.efficiency * 100)}%`;

            const downloadLink = clone.querySelector('.download-midi');
            downloadLink.style.display = 'none';

            const canvas = clone.querySelector('.waveform-canvas');
            container.appendChild(clone);
            requestAnimationFrame(() => renderWaveform(canvas, session));
        });

    } catch (error) {
        console.error('Error fetching sessions:', error);
    }
}

async function fetchMonthStats(year, month) {
    try {
        const response = await fetch(`/api/month_stats?year=${year}&month=${month}`);
        const data = await response.json();

        renderCalendar(data.daily_map, year, month);
        renderMonthlyReport(data.report);
    } catch (e) {
        console.error("Error fetching month stats", e);
    }
}

function renderCalendar(dailyMap, year, month) {
    const container = document.getElementById('heatmap-container');
    container.innerHTML = '';

    const monthLabel = document.getElementById('calendar-month-label');
    const dateObj = new Date(year, month - 1, 1);
    monthLabel.textContent = dateObj.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' });

    // Days in month
    const daysInMonth = new Date(year, month, 0).getDate();
    const firstDayDow = new Date(year, month - 1, 1).getDay(); // 0 sent -> 6 sat

    // Padding for start (0=Sun)
    for (let i = 0; i < firstDayDow; i++) {
        const cell = document.createElement('div');
        cell.className = 'heatmap-cell empty';
        cell.style.visibility = 'hidden';
        container.appendChild(cell);
    }

    for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = `${year}-${month.toString().padStart(2, '0')}-${d.toString().padStart(2, '0')}`;
        const activeSeconds = dailyMap[dateStr] || 0;

        const cell = document.createElement('div');
        cell.className = 'heatmap-cell';
        if (activeSeconds > 0) cell.classList.add('has-data');

        // Color scale
        if (activeSeconds > 0) {
            const mins = Math.round(activeSeconds / 60);
            cell.title = `${dateStr}: ${mins} min`;

            // Content: Day number + Active Mins
            cell.innerHTML = `
                <span class="day-number">${d}</span>
                <span class="cell-mins">${mins}<br>min</span>
            `;

            if (activeSeconds > 3600) cell.style.backgroundColor = '#404040'; // > 60m
            else if (activeSeconds > 1800) cell.style.backgroundColor = '#808080'; // > 30m
            else if (activeSeconds > 900) cell.style.backgroundColor = '#B0B0B0'; // > 15m
            else cell.style.backgroundColor = '#D6D6D6';

            // Text color contrast
            cell.style.color = '#FFF';
        } else {
            // Just day number
            cell.innerHTML = `<span class="day-number">${d}</span>`;
        }

        container.appendChild(cell);
    }
}

function renderMonthlyReport(report) {
    document.getElementById('month-audio').textContent = `${(report.total_audio_duration / 60).toFixed(1)} min`;
    document.getElementById('month-active').textContent = `${(report.total_active_duration / 60).toFixed(1)} min`;
    document.getElementById('month-keystrokes').textContent = report.total_keystrokes.toLocaleString();
    document.getElementById('month-efficiency').textContent = `${Math.round(report.efficiency * 100)}%`;
}

// Display in minutes with 1 decimal place
function formatDuration(seconds) {
    const minutes = seconds / 60;
    return `${minutes.toFixed(1)} min`;
}

function renderWaveform(canvas, session) {
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;
    const centerY = height / 2;

    ctx.clearRect(0, 0, width, height);

    const envelope = session.waveform;
    if (!envelope || envelope.length === 0) return;

    // Waveform
    ctx.fillStyle = '#E0E0E0';
    ctx.beginPath();
    ctx.moveTo(0, centerY);

    for (let i = 0; i < envelope.length; i++) {
        const x = (i / envelope.length) * width;
        const amp = envelope[i];
        const y = centerY - (amp * height / 2);
        ctx.lineTo(x, y);
    }
    for (let i = envelope.length - 1; i >= 0; i--) {
        const x = (i / envelope.length) * width;
        const amp = envelope[i];
        const y = centerY + (amp * height / 2);
        ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();

    // Intervals
    ctx.fillStyle = 'rgba(0, 122, 255, 0.1)';
    const totalDuration = session.total_duration;

    if (session.intervals) {
        session.intervals.forEach(interval => {
            const [start, end] = interval;
            const startX = (start / totalDuration) * width;
            const endX = (end / totalDuration) * width;
            const w = endX - startX;
            ctx.fillRect(startX, 0, w, height);
        });
    }
}
