(function () {
    'use strict';

    var root = document.querySelector('[data-rb-chatbot]');
    if (!root) return;

    var panel = root.querySelector('#rb-help-panel');
    var openButton = root.querySelector('[data-rb-chat-open]');
    var closeButton = root.querySelector('[data-rb-chat-close]');
    var form = root.querySelector('[data-rb-chat-form]');
    var input = root.querySelector('[data-rb-chat-input]');
    var sendButton = root.querySelector('[data-rb-chat-send]');
    var messages = root.querySelector('.rb-help__messages');
    var status = root.querySelector('[data-rb-chat-status]');
    var endpoint = root.getAttribute('data-endpoint');
    var isSending = false;

    function setOpen(isOpen) {
        panel.hidden = !isOpen;
        openButton.setAttribute('aria-expanded', String(isOpen));
        if (isOpen) input.focus();
        else openButton.focus();
    }

    function addMessage(text, kind) {
        var bubble = document.createElement('p');
        bubble.className = 'rb-help__bubble rb-help__bubble--' + kind;
        bubble.textContent = text;
        messages.appendChild(bubble);
        messages.scrollTop = messages.scrollHeight;
    }

    function sendQuestion(question) {
        var text = (question || '').trim();
        if (isSending) return;
        if (!text) {
            status.textContent = 'Enter a question to continue.';
            input.focus();
            return;
        }
        if (text.length > 1200) {
            status.textContent = 'Please keep your question under 1200 characters.';
            return;
        }
        setOpen(true);
        isSending = true;
        addMessage(text, 'user');
        input.value = '';
        input.disabled = true;
        sendButton.disabled = true;
        root.querySelectorAll('[data-rb-chat-question]').forEach(function (button) {
            button.disabled = true;
        });
        status.textContent = 'Getting an answer…';

        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.RescueBite.getCSRF()
            },
            body: JSON.stringify({ message: text })
        }).then(function (response) {
            return response.json().then(function (body) {
                if (!response.ok) throw new Error(body.error || 'Please try again.');
                return body;
            });
        }).then(function (body) {
            addMessage(body.reply, 'assistant');
            status.textContent = '';
        }).catch(function () {
            addMessage("I'm currently unable to connect to the help service. You can still explore the application using the options on this page.", 'assistant');
            status.textContent = '';
        }).finally(function () {
            isSending = false;
            input.disabled = false;
            sendButton.disabled = false;
            root.querySelectorAll('[data-rb-chat-question]').forEach(function (button) {
                button.disabled = false;
            });
            if (!panel.hidden) input.focus();
        });
    }

    openButton.addEventListener('click', function () { setOpen(panel.hidden); });
    closeButton.addEventListener('click', function () { setOpen(false); });
    form.addEventListener('submit', function (event) {
        event.preventDefault();
        sendQuestion(input.value);
    });
    input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    root.querySelectorAll('[data-rb-chat-question]').forEach(function (button) {
        button.addEventListener('click', function () {
            sendQuestion(button.getAttribute('data-rb-chat-question'));
        });
    });
}());
