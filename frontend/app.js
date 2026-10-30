/**
 * Sana'a AI — Chatbot Client Application
 * Connects the Figma UI to FastAPI backend (/api/v1/chat)
 */

(function () {
  'use strict';

  // --- Configuration & State ---
  const API_CHAT_URL = '/api/v1/chat';
  const API_RESET_URL = '/api/v1/chat/reset';
  const STORAGE_KEY_SESSION = 'sanaa_session_id';

  let currentSessionId = getOrCreateSessionId();
  let isWaitingForResponse = false;

  // --- DOM Elements ---
  const chatMessagesEl = document.getElementById('chatMessages');
  const chatInputEl = document.getElementById('chatInput');
  const sendBtnEl = document.getElementById('sendBtn');
  const newChatBtnEl = document.getElementById('newChatBtn');

  // Sidebar Elements
  const sidebarPillEl = document.getElementById('sidebarPill');
  const sidebarTitleEl = document.getElementById('sidebarTitle');
  const sidebarDescEl = document.getElementById('sidebarDesc');
  const sidebarFooterNoteEl = document.getElementById('sidebarFooterNote');
  const sidebarActionsListEl = document.getElementById('sidebarActionsList');

  // --- Initialize ---
  function init() {
    setupEventListeners();
    renderWelcomeMessage();
  }

  // --- Session Management ---
  function getOrCreateSessionId() {
    let sid = localStorage.getItem(STORAGE_KEY_SESSION);
    if (!sid) {
      sid = 'sanaa-sess-' + Math.random().toString(36).substring(2, 10) + '-' + Date.now();
      localStorage.setItem(STORAGE_KEY_SESSION, sid);
    }
    return sid;
  }

  function resetSession() {
    if (isWaitingForResponse) return;

    fetch(API_RESET_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId }),
    })
      .catch((err) => console.warn('Reset endpoint warning:', err))
      .finally(() => {
        // Generate new session ID and clear UI
        currentSessionId = 'sanaa-sess-' + Math.random().toString(36).substring(2, 10) + '-' + Date.now();
        localStorage.setItem(STORAGE_KEY_SESSION, currentSessionId);
        chatMessagesEl.innerHTML = '';
        resetSidebarToDefault();
        renderWelcomeMessage();
      });
  }

  // --- Event Listeners ---
  function setupEventListeners() {
    // Send Button click
    sendBtnEl.addEventListener('click', handleSendMessage);

    // Enter to send (Shift+Enter for newline)
    chatInputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
      }
    });

    // Auto-expand textarea height
    chatInputEl.addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 120) + 'px';

      // Auto-adjust direction if user starts with English letters
      const firstChar = this.value.trim().charAt(0);
      if (firstChar && /[a-zA-Z]/.test(firstChar)) {
        this.style.direction = 'ltr';
        this.style.textAlign = 'left';
      } else {
        this.style.direction = 'rtl';
        this.style.textAlign = 'right';
      }
    });

    // New Chat Button
    if (newChatBtnEl) {
      newChatBtnEl.addEventListener('click', resetSession);
    }
  }

  // --- Send Message Flow ---
  async function handleSendMessage() {
    const rawText = chatInputEl.value.trim();
    if (!rawText || isWaitingForResponse) return;

    // 1. Render User Message in Chat
    renderUserMessage(rawText);

    // 2. Clear input
    chatInputEl.value = '';
    chatInputEl.style.height = 'auto';
    chatInputEl.focus();

    // 3. Show typing indicator
    isWaitingForResponse = true;
    sendBtnEl.disabled = true;
    const typingIndicatorEl = renderTypingIndicator();
    scrollToBottom();

    // 4. Send API Request
    try {
      const response = await fetch(API_CHAT_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          session_id: currentSessionId,
          message: rawText,
          language: 'auto',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server returned error status ${response.status}`);
      }

      const data = await response.json();

      // Remove typing indicator
      typingIndicatorEl.remove();

      // 5. Render Assistant Reply
      renderAssistantMessage(data);

      // 6. Update Sidebar with Escalation & Booking context
      updateSidebarFromResponse(data);

    } catch (error) {
      console.error('Chat API Error:', error);
      typingIndicatorEl.remove();
      renderErrorMessage(
        'عذراً، حدث خطأ أثناء الاتصال بالخادم. يرجى التأكد من تشغيل السيرفر والمحاولة مرة أخرى.'
      );
    } finally {
      isWaitingForResponse = false;
      sendBtnEl.disabled = false;
      scrollToBottom();
    }
  }

  // --- Message Renderers ---

  function renderUserMessage(text) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const row = document.createElement('div');
    row.className = 'message-row user';

    const isEnglish = isTextEnglish(text);
    const dirAttr = isEnglish ? 'dir="ltr" style="text-align: left;"' : '';

    row.innerHTML = `
      <div class="user-bubble" ${dirAttr}>
        <div>${escapeHtml(text)}</div>
        <span class="msg-time">${timeStr}</span>
      </div>
    `;

    chatMessagesEl.appendChild(row);
    scrollToBottom();
  }

  function renderAssistantMessage(data) {
    const row = document.createElement('div');
    row.className = 'message-row assistant';

    const isEnglish = isTextEnglish(data.reply);
    const dirAttr = isEnglish ? 'dir="ltr" style="text-align: left;"' : '';

    const formattedReplyHtml = formatMarkdown(data.reply);

    // Build sub-cards
    let extraCardsHtml = '';

    // 1. Critical Life-Threat Emergency Banner
    if (data.escalation_details && data.escalation_details.life_threatening_emergency) {
      const contacts = data.escalation_details.emergency_contacts || {};
      let hotlinesHtml = '';

      if (contacts.gas) {
        hotlinesHtml += `<a href="tel:${contacts.gas}" class="hotline-btn">📞 طوارئ الغاز (${contacts.gas})</a>`;
      }
      if (contacts.electricity) {
        hotlinesHtml += `<a href="tel:${contacts.electricity}" class="hotline-btn">⚡ طوارئ الكهرباء (${contacts.electricity})</a>`;
      }
      if (contacts.fire) {
        hotlinesHtml += `<a href="tel:${contacts.fire}" class="hotline-btn">🚒 المطافئ (${contacts.fire})</a>`;
      }
      if (contacts.ambulance) {
        hotlinesHtml += `<a href="tel:${contacts.ambulance}" class="hotline-btn">🚑 الإسعاف (${contacts.ambulance})</a>`;
      }

      extraCardsHtml += `
        <div class="emergency-threat-banner">
          <div class="emergency-threat-title">
            ⚠️ تنبيه أمان عاجل — خطر حرج على السلامة
          </div>
          <div>${data.safety_warning || 'يرجى إخلاء المنطقة فوراً والاتصال بخدمات الطوارئ المختصة.'}</div>
          <div class="emergency-hotline-pills">
            ${hotlinesHtml}
          </div>
        </div>
      `;
    }
    // 2. Safety Warning Banner (Medium / High)
    else if (data.safety_warning) {
      extraCardsHtml += `
        <div class="safety-warning-banner">
          <span>⚠️</span>
          <div>${escapeHtml(data.safety_warning)}</div>
        </div>
      `;
    }

    // 3. Suggested Actions / Steps (Figma style action card)
    if (data.suggested_actions && data.suggested_actions.length > 0) {
      const actionsList = data.suggested_actions
        .map((act) => `<li>• ${escapeHtml(act)}</li>`)
        .join('');

      extraCardsHtml += `
        <div class="chat-action-card">
          <span class="chat-action-pill">خطوات موصى بها</span>
          <ul style="list-style: none; padding: 0; margin-top: 6px; font-size: 13px; line-height: 1.6;">
            ${actionsList}
          </ul>
        </div>
      `;
    }

    // 4. Technician Booking Pathways (Standard vs Emergency Maintenance)
    if (data.escalation_details && !data.escalation_details.life_threatening_emergency) {
      const pathway = data.escalation_details.booking_pathway;
      const specialist = data.escalation_details.recommended_specialist || 'فني صيانة معتمد';

      if (pathway === 'EMERGENCY_MAINTENANCE') {
        extraCardsHtml += `
          <div class="booking-pathway-card">
            <span class="booking-pathway-badge emergency">🚨 صيانة طارئة مستعجلة</span>
            <div style="font-size: 13px; font-weight: 600; color: #fff;">
              ${escapeHtml(specialist)}
            </div>
            <div style="font-size: 12px; color: #cbd5e1; margin-top: 4px;">
              ${escapeHtml(data.escalation_details.booking_urgency_reason || 'يتطلب تدخلاً سريعاً في نفس اليوم.')}
            </div>
            <button class="booking-btn emergency" onclick="alert('سيتم توجيهك لخدمة الطوارئ السريعة عبر منصة صَنعة.')">
              طلب فني طوارئ صَنعة الآن (وصول فوري)
            </button>
          </div>
        `;
      } else if (pathway === 'STANDARD') {
        extraCardsHtml += `
          <div class="booking-pathway-card">
            <span class="booking-pathway-badge standard">📅 حجز موعد صيانة</span>
            <div style="font-size: 13px; font-weight: 600; color: #fff;">
              ${escapeHtml(specialist)}
            </div>
            <div style="font-size: 12px; color: #cbd5e1; margin-top: 4px;">
              ${escapeHtml(data.escalation_details.booking_urgency_reason || 'يمكن جدولة الزيارة في الموعد الأنسب لك.')}
            </div>
            <button class="booking-btn standard" onclick="alert('سيتم توجيهك لجدولة موعد الفني عبر منصة صَنعة.')">
              جدولة موعد زيارة الفني
            </button>
          </div>
        `;
      }
    }

    row.innerHTML = `
      <div class="assistant-bubble" ${dirAttr}>
        <div>${formattedReplyHtml}</div>
        ${extraCardsHtml}
      </div>
    `;

    chatMessagesEl.appendChild(row);
    scrollToBottom();
  }

  function renderErrorMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.innerHTML = `
      <div class="assistant-bubble" style="background-color: #7f1d1d; border: 1px solid #dc2626;">
        <div style="display: flex; align-items: center; gap: 8px; font-weight: 700;">
          <span>❌</span>
          <span>تنبيه خطأ في النظام</span>
        </div>
        <p style="margin-top: 6px; font-size: 13px;">${escapeHtml(text)}</p>
      </div>
    `;
    chatMessagesEl.appendChild(row);
    scrollToBottom();
  }

  function renderTypingIndicator() {
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.id = 'typingIndicatorRow';
    row.innerHTML = `
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    `;
    chatMessagesEl.appendChild(row);
    return row;
  }

  function renderWelcomeMessage() {
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.innerHTML = `
      <div class="assistant-bubble">
        <p><strong>أهلاً بك في "صَنعة"! 👋</strong></p>
        <p>أنا مساعدك الذكي المتخصص في صيانة الأجهزة المنزلية والأعمال الفنية (غسالات، ثلاجات، كهرباء، سباكة، ودهانات).</p>
        <p>أقدر أساعدك في تشخيص الأعطال، إعطائك خطوات فحص آمنة بنفسك، أو ترشيح فني معتمد لحجز موعده عبر المنصة.</p>
        <div class="chat-action-card" style="margin-top: 10px;">
          <span class="chat-action-pill">أمثلة تقدر تسألني عنها</span>
          <div style="font-size: 13px; color: #cbd5e1; display: flex; flex-direction: column; gap: 6px; margin-top: 6px;">
            <span style="cursor: pointer; text-decoration: underline;" onclick="document.getElementById('chatInput').value='الغسالة بتنزل مية ومش بتعصر'; document.getElementById('chatInput').focus();">• "الغسالة بتنزل مية ومش بتعصر"</span>
            <span style="cursor: pointer; text-decoration: underline;" onclick="document.getElementById('chatInput').value='الثلاجة بتعمل صوت تكتكة والفريزر مبيجمدش'; document.getElementById('chatInput').focus();">• "الثلاجة بتعمل صوت تكتكة والفريزر مبيجمدش"</span>
            <span style="cursor: pointer; text-decoration: underline;" onclick="document.getElementById('chatInput').value='إزاي أنضف فلتر الغسالة بأمان؟'; document.getElementById('chatInput').focus();">• "إزاي أنضف فلتر الغسالة بأمان؟"</span>
          </div>
        </div>
      </div>
    `;
    chatMessagesEl.appendChild(row);
  }

  // --- Dynamic Sidebar Updater ---
  function updateSidebarFromResponse(data) {
    if (!data.escalation_details) return;

    const details = data.escalation_details;

    // 1. Life Threatening Hazard
    if (details.life_threatening_emergency) {
      sidebarPillEl.textContent = 'خطر طارئ عاجل';
      sidebarPillEl.style.backgroundColor = '#fecaca';
      sidebarPillEl.style.color = '#dc2626';

      sidebarTitleEl.textContent = 'أولوية الإخلاء والطوارئ';
      sidebarDescEl.textContent = 'تم تعليق حجز الصيانة التجارية مؤقتاً لحين زوال الخطر وتأمين الموقع.';
      sidebarFooterNoteEl.textContent = 'اتصل فوراً بخدمات الطوارئ الرسمية المعروضة في المحادثة من مكان آمن.';

      renderSidebarActionItems([
        'الابتعاد الفوري عن منطقة الخطر',
        'عدم ملامسة أي مفاتيح كهربائية',
        'الاتصال بطوارئ المرافق الرسمية'
      ]);
      return;
    }

    // 2. Emergency Maintenance
    if (details.booking_pathway === 'EMERGENCY_MAINTENANCE') {
      sidebarPillEl.textContent = 'صيانة طارئة مستعجلة';
      sidebarPillEl.style.backgroundColor = '#fed7aa';
      sidebarPillEl.style.color = '#c2410c';

      sidebarTitleEl.textContent = details.recommended_specialist || 'فني صيانة طوارئ';
      sidebarDescEl.textContent = details.booking_urgency_reason || 'عطل عاجل يتطلب فحص فني في أسرع وقت.';
      sidebarFooterNoteEl.textContent = 'يمكنك طلب الفني فوراً من زر الحجز السريع في الرسالة.';

      renderSidebarActionItems(data.suggested_actions || []);
      return;
    }

    // 3. Standard Booking
    if (details.booking_pathway === 'STANDARD') {
      sidebarPillEl.textContent = 'حجز فني معتمد';
      sidebarPillEl.style.backgroundColor = '#e0f2fe';
      sidebarPillEl.style.color = '#0284c7';

      sidebarTitleEl.textContent = details.recommended_specialist || 'فني صيانة معتمد';
      sidebarDescEl.textContent = details.booking_urgency_reason || 'عطل يتطلب فحصاً ميكانيكياً متخصصاً.';
      sidebarFooterNoteEl.textContent = 'حدد الوقت الأنسب لك لحجز زيارة الفني عبر صَنعة.';

      renderSidebarActionItems(data.suggested_actions || []);
      return;
    }

    // 4. DIY Guidance (Default)
    sidebarPillEl.textContent = 'جرب قبل الاستعانة بفني';
    sidebarPillEl.style.backgroundColor = 'var(--teal-light-bg)';
    sidebarPillEl.style.color = 'var(--teal-light-text)';

    sidebarTitleEl.textContent = 'جرب بنفسك خطوات بسيطة';
    sidebarDescEl.textContent = 'خطوات فحص وتنظيف وقائية آمنة يمكنك تطبيقها في دقائق.';
    sidebarFooterNoteEl.textContent = 'ممكن تجرب الحلول دي بنفسك قبل ما تطلب فني.';

    renderSidebarActionItems(data.suggested_actions || [
      'فصل فيشة الكهرباء قبل الفحص',
      'التأكد من سلامة الخراطيم والتوصيلات',
      'تنظيف الفلاتر والأجزاء الخارجية'
    ]);
  }

  function renderSidebarActionItems(items) {
    if (!sidebarActionsListEl) return;
    if (!items || items.length === 0) {
      sidebarActionsListEl.innerHTML = '';
      return;
    }

    sidebarActionsListEl.innerHTML = items
      .slice(0, 4)
      .map(
        (item) => `
        <li class="sidebar-action-item">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span>${escapeHtml(item)}</span>
        </li>
      `
      )
      .join('');
  }

  function resetSidebarToDefault() {
    sidebarPillEl.textContent = 'جرب قبل الاستعانة بفني';
    sidebarPillEl.style.backgroundColor = 'var(--teal-light-bg)';
    sidebarPillEl.style.color = 'var(--teal-light-text)';
    sidebarTitleEl.textContent = 'جرب بنفسك خطوات بسيطة';
    sidebarDescEl.textContent = 'لتغيير الجوان المطاطي أو تنظيف الحنفية.';
    sidebarFooterNoteEl.textContent = 'ممكن تجرب الحلول دي بنفسك قبل ما تطلب فني.';
    if (sidebarActionsListEl) sidebarActionsListEl.innerHTML = '';
  }

  // --- Utilities ---
  function scrollToBottom() {
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  }

  function isTextEnglish(text) {
    if (!text) return false;
    const arabicPattern = /[\u0600-\u06FF]/;
    const englishPattern = /[a-zA-Z]/;
    const arabicMatches = (text.match(/[\u0600-\u06FF]/g) || []).length;
    const englishMatches = (text.match(/[a-zA-Z]/g) || []).length;
    return englishMatches > arabicMatches && !arabicPattern.test(text.substring(0, 10));
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Numbered lists: 1. text
    html = html.replace(/(?:^|\n)(\d+)\.\s+(.*)/g, '<br/><strong>$1.</strong> $2');

    // Bullet points: * or -
    html = html.replace(/(?:^|\n)[*-]\s+(.*)/g, '<br/>• $1');

    // Paragraph line breaks
    html = html.replace(/\n\n/g, '<br/><br/>');
    html = html.replace(/\n/g, '<br/>');

    return html;
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
