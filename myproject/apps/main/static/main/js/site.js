/*
 * RescueBite Design System - shared behaviour.
 * Small, dependency-free helpers used by every page, plus the tab component.
 */
(function () {
    'use strict';

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    function getCookie(name) {
        var match = document.cookie.split('; ').find(function (row) {
            return row.indexOf(name + '=') === 0;
        });
        return match ? match.split('=')[1] : null;
    }

    function getCSRF() {
        var fromCookie = getCookie('csrftoken');
        if (fromCookie) {
            return fromCookie;
        }
        var field = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return field ? field.value : null;
    }

    var toastHost = null;

    function toastHostEl() {
        if (!toastHost) {
            toastHost = document.createElement('div');
            toastHost.className = 'rb-toast-host';
            document.body.appendChild(toastHost);
        }
        return toastHost;
    }

    function dismiss(el) {
        el.remove();
    }

    /* Prefer the page's Bootstrap toast when present, otherwise fall back to
       the design-system toast. Both are announced via aria-live. */
    function toast(message, variant) {
        variant = variant || 'success';

        var existing = document.getElementById('liveToast');
        var textNode = document.getElementById('toastText');
        if (existing && textNode && typeof window.bootstrap !== 'undefined' &&
            window.bootstrap.Toast) {
            textNode.innerText = message;
            window.bootstrap.Toast.getOrCreateInstance(existing, { delay: 4000 }).show();
            return;
        }

        var el = document.createElement('div');
        el.className = 'rb-toast rb-toast--' + (variant === 'error' ? 'error' : variant);
        el.setAttribute('role', variant === 'error' ? 'alert' : 'status');
        el.textContent = message;

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'rb-toast__close';
        close.innerHTML = '&times;';
        close.setAttribute('aria-label', 'Dismiss notification');
        close.addEventListener('click', function () {
            dismiss(el);
        });
        el.appendChild(close);

        toastHostEl().appendChild(el);
        window.setTimeout(function () {
            dismiss(el);
        }, 4000);
    }

    // A panel belongs to a tab group when one of that group's tabs names it,
    // either through `aria-controls` or through the matching `data-rb-panel`
    // value. Panels live outside the tab strip, so they are found from the
    // shared parent scope rather than from inside the group.
    function ownsPanel(group, panel) {
        var panelName = panel.getAttribute('data-rb-panel');
        return Array.prototype.some.call(group.querySelectorAll('[data-rb-tab]'),
            function (tab) {
                return tab.getAttribute('aria-controls') === panel.id ||
                    tab.getAttribute('data-rb-tab') === panelName;
            });
    }

    function activateTab(group, tab) {
        var name = tab.getAttribute('data-rb-tab');
        var targetId = tab.getAttribute('aria-controls');

        group.querySelectorAll('[data-rb-tab]').forEach(function (btn) {
            var isActive = btn === tab;
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
            btn.classList.toggle('rb-tab--active', isActive);
            btn.tabIndex = isActive ? 0 : -1;
        });

        var scope = group.parentNode || document;
        Array.prototype.slice.call(scope.querySelectorAll('[data-rb-panel]'))
            .filter(function (panel) { return ownsPanel(group, panel); })
            .forEach(function (panel) {
                var isActive = (targetId && panel.id === targetId) ||
                    panel.getAttribute('data-rb-panel') === name;
                panel.classList.toggle('is-active', isActive);
                panel.hidden = !isActive;
            });
    }

    function initTabs(root) {
        (root || document).querySelectorAll('[data-rb-tabs]').forEach(function (group) {
            if (group.dataset.rbTabsReady === 'true') {
                return;
            }
            group.dataset.rbTabsReady = 'true';

            var tabs = Array.prototype.slice.call(group.querySelectorAll('[data-rb-tab]'));

            // The panels are siblings of the tab strip, so reconcile them once at
            // init against the server-rendered `is-active` markup. Only panels
            // belonging to this group are touched, so several tab groups can
            // coexist under one parent without hiding each other.
            var scope = group.parentNode || document;
            Array.prototype.slice.call(scope.querySelectorAll('[data-rb-panel]'))
                .filter(function (panel) { return ownsPanel(group, panel); })
                .forEach(function (panel) {
                    panel.hidden = !panel.classList.contains('is-active');
                });

            tabs.forEach(function (tab) {
                tab.addEventListener('click', function () {
                    activateTab(group, tab);
                });
            });

            group.addEventListener('keydown', function (event) {
                var index = tabs.indexOf(document.activeElement);
                if (index === -1) {
                    return;
                }
                var next = null;
                if (event.key === 'ArrowRight') {
                    next = tabs[(index + 1) % tabs.length];
                } else if (event.key === 'ArrowLeft') {
                    next = tabs[(index - 1 + tabs.length) % tabs.length];
                } else if (event.key === 'Home') {
                    next = tabs[0];
                } else if (event.key === 'End') {
                    next = tabs[tabs.length - 1];
                }
                if (next) {
                    event.preventDefault();
                    next.focus();
                    activateTab(group, next);
                }
            });
        });
    }

    function initScrollLinks(root) {
        (root || document).querySelectorAll('[data-rb-scroll-to]').forEach(function (link) {
            link.addEventListener('click', function (event) {
                var target = document.querySelector(link.getAttribute('data-rb-scroll-to'));
                if (!target) {
                    return;
                }
                event.preventDefault();
                target.scrollIntoView({
                    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
                        ? 'auto'
                        : 'smooth',
                    block: 'start'
                });
            });
        });
    }

    /*
     * Optional image preview for file inputs.
     * Opt-in per input with data-rb-preview="#selectorOfThePreviewBox".
     */
    function initImagePreviews(root) {
        (root || document).querySelectorAll('input[type="file"][data-rb-preview]').forEach(function (input) {
            var box = document.querySelector(input.getAttribute('data-rb-preview'));
            if (!box) {
                return;
            }
            var img = box.querySelector('img');
            if (!img) {
                return;
            }

            input.addEventListener('change', function () {
                var file = input.files && input.files[0];
                if (!file || !/^image\//.test(file.type)) {
                    box.classList.remove('is-visible');
                    img.removeAttribute('src');
                    return;
                }
                var reader = new FileReader();
                reader.addEventListener('load', function () {
                    img.src = reader.result;
                    box.classList.add('is-visible');
                });
                reader.readAsDataURL(file);
            });
        });
    }

    window.RescueBite = {
        onReady: onReady,
        getCookie: getCookie,
        getCSRF: getCSRF,
        toast: toast,
        initTabs: initTabs,
        initScrollLinks: initScrollLinks,
        initImagePreviews: initImagePreviews
    };

    onReady(function () {
        initTabs(document);
        initScrollLinks(document);
        initImagePreviews(document);
    });
}());