/**
 * Global background batch-grading watcher — survives page navigation.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'btec_bg_grading';
    var pollTimer = null;
    var completionToken = null;
    var stalePollCount = 0;

    function gradingPageUrl(assignmentId) {
        return '/batch-grade/' + Number(assignmentId) + '?resume_grading=1';
    }

    function openBgBatchResultsSafe(batchId) {
        var state = readState();
        var assignmentId = state && state.assignmentId;
        if (!batchId || !assignmentId) return;

        function go(id) {
            window.location.href = '/batch-results/' + id;
        }

        fetch('/api/batch-meta/' + batchId)
            .then(function (res) { return res.json(); })
            .then(function (meta) {
                if (meta.found) {
                    go(batchId);
                    return;
                }
                return fetch('/api/batch-grade-latest/' + assignmentId)
                    .then(function (r) { return r.json(); })
                    .then(function (latest) {
                        if (latest.found && latest.batch_id && latest.status === 'completed') {
                            return fetch('/api/batch-meta/' + latest.batch_id)
                                .then(function (r2) { return r2.json(); })
                                .then(function (m2) {
                                    if (m2.found) go(latest.batch_id);
                                    else orphanAlert(batchId);
                                });
                        } else {
                            orphanAlert(batchId);
                        }
                    });
            })
            .catch(function () {
                orphanAlert(batchId);
            });
    }

    function orphanAlert(batchId) {
        writeState(null);
        alert(
            'الدفعة #' + batchId + ' غير محفوظة في قاعدة البيانات. أعد التصحيح PRO من صفحة المهمة.'
        );
    }

    function readState() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (_) {
            return null;
        }
    }

    function writeState(data) {
        if (data) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } else {
            localStorage.removeItem(STORAGE_KEY);
        }
    }

    function resolveBatchErrorMessage(source) {
        if (!source) return 'فشل التصحيح';
        var fr = source.final_response || source;
        var errors = fr.errors || source.errors || [];
        var first = errors.length ? errors[0] : null;
        var raw = (first && first.error)
            || source.detail_ar
            || fr.detail_ar
            || source.error
            || fr.detail
            || source.detail
            || '';
        var low = String(raw).toLowerCase();
        var prefix = first && first.student ? (first.student + ' — ') : '';
        if (low.indexOf('429') >= 0 || low.indexOf('depleted') >= 0 || low.indexOf('resource_exhausted') >= 0) {
            return prefix + 'نفد رصيد مزود الذكاء الاصطناعي (Gemini). شحن الحساب من Google AI Studio ثم أعد المحاولة.';
        }
        if (low.indexOf('402') >= 0 || low.indexOf('insufficient') >= 0 || low.indexOf('quota') >= 0) {
            return prefix + 'رصيد الذكاء الاصطناعي غير كافٍ — راجع الفوترة ثم أعد المحاولة.';
        }
        return prefix + (raw || 'فشل التصحيح');
    }

    function resolveProgressPercent(info) {
        if (!info || !info.found) {
            return null;
        }
        if (info.finished) {
            return 100;
        }
        var total = Math.max(
            Number(info.total) || 0,
            (info.all_student_names || []).length,
            1
        );
        var completed = Math.min(Number(info.completed) || 0, total);
        var sp = Number(info.student_progress) || 0;
        if (typeof info.percent === 'number' && !Number.isNaN(info.percent) && info.percent > 0) {
            return Math.max(1, Math.min(99, Math.round(info.percent)));
        }
        if (total > 0 && (completed > 0 || sp > 0)) {
            return Math.max(1, Math.min(99, Math.round(((completed + sp) / total) * 100)));
        }
        var phase = info.current_phase || '';
        if (phase === 'extracting_archive') return 8;
        if (phase === 'extracting') return 14;
        if (phase === 'vision') return 28;
        if (phase === 'grading') return 45;
        if (phase === 'saving') return 92;
        if (info.current_student) return 12;
        return 3;
    }

    function ensureFloater() {
        var el = document.getElementById('bgGradingFloater');
        if (el) return el;
        el = document.createElement('div');
        el.id = 'bgGradingFloater';
        el.className = 'bg-grading-floater hidden';
        el.innerHTML =
            '<button type="button" class="bg-grading-floater-main" id="bgGradingFloaterBtn" title="العودة لصفحة التصحيح">' +
            '<span class="bg-grading-floater-icon" aria-hidden="true">' +
            '<span class="bg-grading-floater-dots">' +
            '<span></span><span></span><span></span><span></span>' +
            '<span></span><span></span><span></span><span></span>' +
            '</span></span>' +
            '<span class="bg-grading-floater-text">' +
            '<strong id="bgGradingFloaterPct">…</strong>' +
            '<small id="bgGradingFloaterLabel">جاري التصحيح...</small>' +
            '</span></button>' +
            '<button type="button" class="bg-grading-floater-close" id="bgGradingFloaterClose" title="إغلاق">×</button>';
        document.body.appendChild(el);
        el.querySelector('#bgGradingFloaterBtn').addEventListener('click', goToGradingPage);
        el.querySelector('#bgGradingFloaterClose').addEventListener('click', function (ev) {
            ev.stopPropagation();
            window.BtecBackgroundGrading.deactivate();
        });
        return el;
    }

    function goToGradingPage() {
        var s = readState();
        if (!s || !s.assignmentId) return;
        window.location.href = gradingPageUrl(s.assignmentId);
    }

    function isOnGradingPage() {
        return /^\/batch-grade\/\d+/.test(window.location.pathname || '');
    }

    function canShowGlobalFloater() {
        var s = readState();
        return !!(s && s.assignmentId && !isOnGradingPage());
    }

    function showFloater() {
        if (!canShowGlobalFloater()) return;
        ensureFloater().classList.remove('hidden');
    }

    function hideFloater() {
        var el = document.getElementById('bgGradingFloater');
        if (el) el.classList.add('hidden');
    }

    function activePercent(percent, state) {
        var pct = Math.round(Number(percent) || 0);
        if (pct > 0) return Math.min(100, pct);
        if (state && state.lastPercent > 0) return Math.min(99, state.lastPercent);
        return 3;
    }

    function updateFloater(percent, label) {
        if (!canShowGlobalFloater()) return;
        showFloater();
        var s = readState();
        var pctEl = document.getElementById('bgGradingFloaterPct');
        var lblEl = document.getElementById('bgGradingFloaterLabel');
        var pct = activePercent(percent, s);
        if (pctEl) pctEl.textContent = pct + '%';
        if (lblEl) lblEl.textContent = label || 'جاري التصحيح...';
    }

    function ensureCompletionModal() {
        var el = document.getElementById('bgGradingCompleteModal');
        if (el) return el;
        el = document.createElement('div');
        el.id = 'bgGradingCompleteModal';
        el.className = 'bg-grading-complete-overlay hidden';
        el.innerHTML =
            '<div class="bg-grading-complete-box">' +
            '<div id="bgGradingCompleteIcon" class="bg-grading-complete-icon">✅</div>' +
            '<h3 id="bgGradingCompleteTitle">اكتمل التصحيح</h3>' +
            '<p id="bgGradingCompleteMsg">انتهى تصحيح الدفعة بنجاح.</p>' +
            '<div class="bg-grading-complete-actions">' +
            '<button type="button" class="bg-grading-btn-primary" id="bgGradingViewResultsBtn">عرض النتائج</button>' +
            '<button type="button" class="bg-grading-btn-secondary" id="bgGradingDismissBtn">لاحقاً</button>' +
            '</div></div>';
        document.body.appendChild(el);
        el.querySelector('#bgGradingDismissBtn').addEventListener('click', function () {
            el.classList.add('hidden');
        });
        return el;
    }

    function showCompletionModal(opts) {
        var modal = ensureCompletionModal();
        var batchId = opts.batchId;
        var token = String(batchId || '') + ':' + String(opts.title || '');
        if (completionToken === token) return;
        completionToken = token;

        document.getElementById('bgGradingCompleteIcon').textContent = opts.icon || '✅';
        document.getElementById('bgGradingCompleteTitle').textContent = opts.title || 'اكتمل التصحيح';
        document.getElementById('bgGradingCompleteMsg').textContent = opts.message || '';

        var viewBtn = document.getElementById('bgGradingViewResultsBtn');
        viewBtn.style.display = batchId ? 'inline-flex' : 'none';
        viewBtn.onclick = function () {
            modal.classList.add('hidden');
            if (batchId) openBgBatchResultsSafe(batchId);
        };

        modal.classList.remove('hidden');

        if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            try {
                var n = new Notification('BTEC Teachers — اكتمل التصحيح', {
                    body: opts.message || 'انتهى تصحيح الدفعة. افتح الموقع لعرض النتائج.',
                    tag: 'btec-bg-grade-' + (batchId || 'done'),
                });
                n.onclick = function () {
                    window.focus();
                    if (batchId) openBgBatchResultsSafe(batchId);
                };
            } catch (_) { /* ignore */ }
        }
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function startPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(tick, 2000);
        tick();
    }

    async function fetchProgress(assignmentId) {
        var res = await fetch('/api/batch-grade-progress/' + assignmentId);
        return res.json();
    }

    async function tryLatestBatch(state) {
        try {
            var res = await fetch('/api/batch-grade-latest/' + state.assignmentId);
            if (!res.ok) return null;
            var latest = await res.json();
            if (!latest.found) return null;
            if (latest.status === 'processing' || latest.status === 'pending') {
                return {
                    found: true,
                    percent: Math.round(
                        ((latest.processed_students || 0) / Math.max(latest.total_students || 1, 1)) * 100
                    ),
                    completed: latest.processed_students || 0,
                    total: latest.total_students || 1,
                    current_phase: 'grading',
                    phase_label: 'جاري التصحيح...',
                    batch_id: latest.batch_id,
                    finished: false,
                };
            }
            if latest.status === 'failed') {
                return {
                    found: true,
                    finished: true,
                    failed: true,
                    error: latest.failure_message || 'توقّف التصحيح — أعد المحاولة',
                    batch_id: latest.batch_id,
                };
            }
            if (latest.status === 'completed' && latest.batch_id) {
                return {
                    found: true,
                    finished: true,
                    percent: 100,
                    final_response: {
                        success: true,
                        batch_id: latest.batch_id,
                        total_students: latest.total_students,
                        processed: latest.processed_students,
                    },
                };
            }
        } catch (_) { /* ignore */ }
        return null;
    }

    async function tick() {
        var state = readState();
        if (!state || !state.assignmentId) {
            stopPolling();
            hideFloater();
            return;
        }

        try {
            var info = await fetchProgress(state.assignmentId);

            if (!info.found) {
                var recovered = await tryLatestBatch(state);
                if (recovered) info = recovered;
                else {
                    stalePollCount++;
                    if (stalePollCount >= 4) {
                        handleFailed(state, 'توقّف التصحيح — لا يوجد تصحيح جارٍ على الخادم.');
                        return;
                    }
                    updateFloater(state.lastPercent || 3, 'جاري التصحيح... (انتظار الخادم)');
                    return;
                }
            }
            stalePollCount = 0;

            if (info.server_restarted) {
                updateFloater(state.lastPercent || 3, info.phase_label || 'جاري استئناف التصحيح...');
                return;
            }
            if (info.finished && info.failed) {
                handleFailed(state, resolveBatchErrorMessage(info) || info.phase_label || 'فشل التصحيح');
                return;
            }

            if (info.batch_id) {
                state.batchId = info.batch_id;
            }
            var pct = resolveProgressPercent(info);
            if (pct !== null) {
                state.lastPercent = pct;
            }
            writeState(state);

            if (info.finished && info.final_response) {
                handleComplete(state, info.final_response);
                return;
            }
            if (info.finished && info.failed) {
                handleFailed(state, resolveBatchErrorMessage(info) || 'فشل التصحيح');
                return;
            }

            var label = info.phase_label || 'جاري التصحيح...';
            if (info.current_student) {
                label += ' — ' + info.current_student;
            }
            updateFloater(pct !== null ? pct : state.lastPercent || 3, label);

            if (typeof window.BtecBackgroundGradingOnProgress === 'function') {
                window.BtecBackgroundGradingOnProgress(info, pct);
            }
        } catch (_) {
            updateFloater(state.lastPercent || 3, 'جاري التصحيح... (إعادة الاتصال)');
        }
    }

    function handleComplete(state, data) {
        stopPolling();
        hideFloater();

        var batchId = (data && data.batch_id) || state.batchId;
        if (!batchId) {
            writeState(null);
            handleFailed(state, 'اكتمل التصحيح لكن لم يُحفظ رقم الدفعة — أعد التصحيح.');
            return;
        }

        fetch('/api/batch-meta/' + batchId)
            .then(function (res) { return res.json(); })
            .then(function (meta) {
                if (!meta.found) {
                    writeState(null);
                    handleFailed(
                        state,
                        'الدفعة #' + batchId + ' غير موجودة في قاعدة البيانات — أعد التصحيح PRO.'
                    );
                    return;
                }
                writeState(null);
                showCompletionModalAfterVerify(state, data, batchId);
            })
            .catch(function () {
                writeState(null);
                showCompletionModalAfterVerify(state, data, batchId);
            });
    }

    function showCompletionModalAfterVerify(state, data, batchId) {
        var cancelled = !!(data && data.cancelled);
        var processed = Number((data && data.processed) || 0);
        var total = Number((data && data.total_students) || 0);
        var msg = cancelled
            ? 'أُوقف التصحيح — النتائج المكتملة محفوظة.'
            : 'تم تصحيح ' + (processed || total || '') + ' طالب/ملف بنجاح.';

        showCompletionModal({
            icon: cancelled ? '⏹️' : '🎉',
            title: cancelled ? 'تم إيقاف التصحيح' : 'اكتمل التصحيح',
            message: msg + '\n\nهل تريد عرض النتائج الآن؟',
            batchId: batchId,
        });
    }

    function handleFailed(state, errorMsg) {
        stopPolling();
        writeState(null);
        hideFloater();
        showCompletionModal({
            icon: '❌',
            title: 'فشل التصحيح',
            message: errorMsg || 'حدث خطأ أثناء التصحيح في الخلفية.',
            batchId: state.batchId || null,
        });
    }

    function requestNotificationPermission() {
        if (typeof Notification === 'undefined') return;
        if (Notification.permission === 'default') {
            Notification.requestPermission().catch(function () { /* ignore */ });
        }
    }

    window.BtecBackgroundGrading = {
        activate: function (opts) {
            if (!opts || !opts.assignmentId) return;
            writeState({
                assignmentId: Number(opts.assignmentId),
                batchId: opts.batchId || null,
                batchName: opts.batchName || '',
                returnUrl: gradingPageUrl(opts.assignmentId),
                startedAt: Date.now(),
                lastPercent: 0,
                overlayDismissed: !!opts.overlayDismissed,
                uploadMode: opts.uploadMode || '',
                archiveScope: opts.archiveScope || 'single',
                studentLabel: opts.studentLabel || '',
            });
            requestNotificationPermission();
            if (opts.overlayDismissed) showFloater();
            startPolling();
        },
        dismissOverlay: function () {
            var s = readState();
            if (!s) return;
            s.overlayDismissed = true;
            s.returnUrl = gradingPageUrl(s.assignmentId);
            if (!s.lastPercent || s.lastPercent < 3) {
                s.lastPercent = 3;
            }
            writeState(s);
            showFloater();
            updateFloater(s.lastPercent, 'جاري التصحيح...');
            tick();
        },
        deactivate: function () {
            writeState(null);
            stopPolling();
            hideFloater();
        },
        isActive: function () {
            return !!readState();
        },
        getContext: function () {
            return readState();
        },
        isOverlayDismissed: function () {
            var s = readState();
            return !!(s && s.overlayDismissed);
        },
        goToGradingPage: goToGradingPage,
        fetchProgress: fetchProgress,
        resolveProgressPercent: resolveProgressPercent,
        handleExternalComplete: function (data) {
            var state = readState();
            if (!state) return false;
            handleComplete(state, data || {});
            return true;
        },
        resumeIfNeeded: function () {
            var s = readState();
            if (!s) return;
            s.returnUrl = gradingPageUrl(s.assignmentId);
            if (!isOnGradingPage()) {
                s.overlayDismissed = true;
            }
            writeState(s);
            startPolling();
        },
        validateOnLoad: async function () {
            var s = readState();
            if (!s || !s.assignmentId) return;
            try {
                var info = await fetchProgress(s.assignmentId);
                if (!info.found) {
                    var recovered = await tryLatestBatch(s);
                    if (recovered) info = recovered;
                }
                if (info.server_restarted) {
                    if (canShowGlobalFloater()) {
                        showFloater();
                        updateFloater(s.lastPercent || 3, info.phase_label || 'جاري استئناف التصحيح...');
                    }
                    return;
                }
                if (info.finished && info.failed) {
                    handleFailed(s, resolveBatchErrorMessage(info) || 'فشل التصحيح');
                    return;
                }
                if (info.finished && info.final_response) {
                    handleComplete(s, info.final_response);
                    return;
                }
                if (canShowGlobalFloater()) {
                    showFloater();
                    var pct = resolveProgressPercent(info);
                    updateFloater(pct !== null ? pct : s.lastPercent, info.phase_label || 'جاري التصحيح...');
                }
            } catch (_) {
                if (canShowGlobalFloater()) {
                    showFloater();
                    updateFloater(s.lastPercent || 3, 'جاري التصحيح...');
                }
            }
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            window.BtecBackgroundGrading.validateOnLoad();
        });
    } else {
        window.BtecBackgroundGrading.validateOnLoad();
    }
})();
