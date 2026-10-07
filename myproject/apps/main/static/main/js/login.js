/*
 * RescueBite - login screen behaviour.

Presentation only. The form keeps posting email/password to the same login
URL with CSRF, so the Django authentication flow and the role-based
redirects are untouched.

Adds:
  - show / hide password toggle on the password field,
  - a clear button that resets the form and re-hides the password,
  - a busy state on submit so a slow authenticate() is not mistaken for a
    dead button.
 */
(function () {
    'use strict';

    var EYE = '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>';
    var EYE_SLASH = '<path d="M3 3l18 18"/><path d="M10.6 10.6a3 3 0 0 0 4.2 4.2"/><path d="M9.9 5.2A9.7 9.7 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-3.2 4.1M6.2 6.2A17.4 17.4 0 0 0 2 12s3.5 7 10 7a9.6 9.6 0 0 0 4.2-.9"/>';

    function iconFor(visible) {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
            + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
            + (visible ? EYE_SLASH : EYE)
            + '</svg>';
    }

    function setReveal(toggle, field, visible) {
        field.type = visible ? 'text' : 'password';
        toggle.setAttribute('aria-pressed', visible ? 'true' : 'false');
        toggle.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
        toggle.setAttribute('title', visible ? 'Hide password' : 'Show password');
        toggle.innerHTML = iconFor(visible);
    }

    function initReveal() {
        var toggle = document.querySelector('[data-rb-reveal]');
        if (!toggle) {
            return null;
        }

        var field = document.getElementById(toggle.getAttribute('data-rb-reveal'));
        if (!field) {
            return null;
        }

        // Normalise whatever the server rendered (always masked) into the
        // collapsed state before the first interaction.
        setReveal(toggle, field, field.type === 'text');

        toggle.addEventListener('click', function () {
            setReveal(toggle, field, field.type === 'password');
        });

        return { toggle: toggle, field: field };
    }

    function initClear(reveal) {
        var clear = document.querySelector('[data-rb-clear]');
        var form = clear && clear.form;
        if (!clear || !form) {
            return;
        }

        clear.addEventListener('click', function () {
            form.reset();

            if (reveal) {
                setReveal(reveal.toggle, reveal.field, false);
            }

            var email = form.querySelector('#id_email');
            if (email) {
                email.focus();
            }
        });
    }

    function initSubmitBusy() {
        var form = document.querySelector('[data-rb-login]');
        if (!form) {
            return;
        }

        form.addEventListener('submit', function () {
            var submit = form.querySelector('button[type="submit"]');
            if (!submit || submit.disabled) {
                return;
            }
            submit.disabled = true;
            submit.setAttribute('aria-busy', 'true');

            var spinner = submit.querySelector('[data-rb-busy]');
            var label = submit.querySelector('[data-rb-submit-label]');
            if (spinner) {
                spinner.hidden = false;
            }
            if (label) {
                label.textContent = 'Signing in\u2026';
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var reveal = initReveal();
        initClear(reveal);
        initSubmitBusy();
    });
}());