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
        document.querySelector('.stat-group:nth-of-type(1) .stat-label').textContent = '今日有效时长';
        document.querySelector('.stat-group:nth-of-type(2) .stat-label').textContent = '今日击键数';
    } else {
        nextBtn.classList.remove('disabled');
        document.querySelector('.stat-group:nth-of-type(1) .stat-label').textContent = '该日有效时长';
        document.querySelector('.stat-group:nth-of-type(2) .stat-label').textContent = '该日击键数';
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
        const groups = await response.json();

        const container = document.getElementById('session-list');
        container.innerHTML = '';

        if (groups.length === 0) {
            container.innerHTML = '<div style="text-align:center; color:#999; padding: 40px;">今日无练习记录</div>';
            return;
        }

        groups.forEach(group => {
            // Create Group Card
            const groupDiv = document.createElement('div');
            groupDiv.className = 'session-group';

            // Calculate Group Audio Duration & Efficiency
            let groupAudioDuration = 0;
            group.sessions.forEach(s => groupAudioDuration += s.total_duration);
            const groupEfficiency = groupAudioDuration > 0 ? (group.active_duration / groupAudioDuration) : 0;

            // Format Time Range
            const startT = new Date(group.start_time);
            const endT = new Date(group.end_time);
            const timeRange = `${startT.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${endT.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;

            // Header
            groupDiv.innerHTML = `
                <div class="group-header">
                    <div class="group-time">${timeRange}</div>
                    <div class="group-stats">
                        <span>录音时长: <strong>${(groupAudioDuration / 60).toFixed(1)} min</strong></span>
                        <span>有效: <strong>${(group.active_duration / 60).toFixed(1)} min</strong></span>
                        <span>效率: <strong>${(groupEfficiency * 100).toFixed(0)}%</strong></span>
                        <span>触键: <strong>${group.keystrokes.toLocaleString()}</strong></span>
                        <span>Sessions: <strong>${group.sessions.length}</strong></span>
                    </div>
                </div>
                <div class="waveform-list"></div>
            `;

            const listContainer = groupDiv.querySelector('.waveform-list');

            // Render Waveforms (Sparklines)
            group.sessions.forEach(session => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'waveform-item';

                // Meta (Duration)
                const mins = (session.active_duration / 60).toFixed(1);

                itemDiv.innerHTML = `
                    <div class="waveform-meta">
                        <div style="font-weight:600; color:#333;">${mins} min</div>
                        <div style="font-size:11px; color:#999; margin-top:2px;">${session.keystrokes.toLocaleString()} 音</div>
                    </div>
                    <div class="waveform-container">
                        <canvas class="waveform-canvas"></canvas>
                    </div>
                `;

                listContainer.appendChild(itemDiv);

                // Render Canvas
                const canvas = itemDiv.querySelector('.waveform-canvas');
                requestAnimationFrame(() => renderSparkline(canvas, session));
            });

            container.appendChild(groupDiv);
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

// Sparkline Renderer (Fixed Height, Full Width)
function renderSparkline(canvas, session) {
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    // Wait for layout? frame request handles it mostly.
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

    // 1. Draw Waveform (Gray)
    ctx.fillStyle = '#E0E0E0';
    ctx.beginPath();
    ctx.moveTo(0, centerY);

    for (let i = 0; i < envelope.length; i++) {
        const x = (i / envelope.length) * width;
        const amp = envelope[i];
        // Scale amp slightly to fill height nicer
        const y = centerY - (amp * height * 0.8 / 2);
        ctx.lineTo(x, y);
    }
    for (let i = envelope.length - 1; i >= 0; i--) {
        const x = (i / envelope.length) * width;
        const amp = envelope[i];
        const y = centerY + (amp * height * 0.8 / 2);
        ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();

    // 2. Draw Inactive Overlay (Slacking) - "Draw overlay on gaps"
    // Semi-transparent overlay on non-active parts
    ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
    const totalDuration = session.total_duration;

    if (session.intervals && session.intervals.length > 0) {
        let lastEnd = 0;
        const sortedIntervals = session.intervals.sort((a, b) => a[0] - b[0]);

        sortedIntervals.forEach(interval => {
            const [start, end] = interval;

            if (start > lastEnd) {
                const gapStart = (lastEnd / totalDuration) * width;
                const gapEnd = (start / totalDuration) * width;
                ctx.fillRect(gapStart, 0, gapEnd - gapStart, height);
            }
            lastEnd = Math.max(lastEnd, end);
        });

        if (lastEnd < totalDuration) {
            const gapStart = (lastEnd / totalDuration) * width;
            const gapEnd = width;
            ctx.fillRect(gapStart, 0, gapEnd - gapStart, height);
        }
    } else {
        // All slacking
        ctx.fillRect(0, 0, width, height);
    }
}
