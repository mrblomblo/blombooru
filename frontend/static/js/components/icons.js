(function () {
    'use strict';

    function normalizeOptions(options, defaultSize, defaultClass, defaultViewBox) {
        if (typeof options === 'number') {
            options = { size: options };
        } else if (typeof options === 'string') {
            options = { class: options };
        } else if (!options || typeof options !== 'object') {
            options = {};
        }

        const size = options.size !== undefined ? options.size : (defaultSize || 16);
        const className = options.class !== undefined ? options.class : (options.className !== undefined ? options.className : (defaultClass || ''));
        const viewBox = options.viewBox || defaultViewBox || '0 0 24 24';
        const id = options.id ? ` id="${options.id}"` : '';
        const style = options.style ? ` style="${options.style}"` : '';
        const extra = options.extra ? ` ${options.extra}` : '';
        const cls = className ? ` class="${className}"` : '';

        return { size, cls, viewBox, id, style, extra };
    }

    function render(name, options, defaultSize, defaultClass, defaultViewBox) {
        const opts = normalizeOptions(options, defaultSize, defaultClass, defaultViewBox);
        return `<svg width="${opts.size}" height="${opts.size}" viewBox="${opts.viewBox}"${opts.cls}${opts.id}${opts.style}${opts.extra}><use href="#icon-${name}"></use></svg>`;
    }

    const Icons = {
        render: function (name, options) {
            return render(name, options);
        },

        // Dice
        dice: function (options) {
            const opts = typeof options === 'object' && options !== null ? options : { face: options };
            let face = opts.face;
            if (face === undefined || face === null || face === 0) {
                face = Math.floor(Math.random() * 6) + 1;
            } else {
                face = Math.max(1, Math.min(6, parseInt(face, 10) || 1));
            }
            return render(`dice-${face}`, opts, 16);
        },

        // Logo
        logo: function (options) {
            return render('logo', options, 28, '', '0 0 28 28');
        },

        // Navigation & Core
        help: (opts) => render('help', opts, 16),
        upload: (opts) => render('upload', opts, 16),
        logout: (opts) => render('logout', opts, 16),
        download: (opts) => render('download', opts, 16),
        share: (opts) => render('share', opts, 16),
        reset: (opts) => render('reset', opts, 14),
        image: (opts) => render('image', opts, 24),
        search: (opts) => render('search', opts, 16),

        // Chevrons & Arrows
        chevron: (direction, opts) => render(`chevron-${direction || 'down'}`, opts, 16),
        chevronDown: (opts) => render('chevron-down', opts, 16),
        chevronUp: (opts) => render('chevron-up', opts, 16),
        chevronLeft: (opts) => render('chevron-left', opts, 16),
        chevronRight: (opts) => render('chevron-right', opts, 16),
        selectArrow: (opts) => render('select-arrow', opts, 12, 'custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary', '0 0 12 12'),
        arrowLeft: (opts) => render('arrow-left', opts, 16),
        arrowRight: (opts) => render('arrow-right', opts, 16),

        // Actions & Editing
        check: (opts) => render('check', opts, 12),
        trash: (opts) => render('trash', opts, 14),
        edit: (opts) => render('edit', opts, 14),
        plus: (opts) => render('plus', opts, 16),
        minus: (opts) => render('minus', opts, 16),
        link: (opts) => render('link', opts, 16),
        close: (opts) => render('close', opts, 14),
        dots: (opts) => render('dots', opts, 16),
        wand: (opts) => render('wand', opts, 16),
        camera: (opts) => render('camera', opts, 16),
        messageSquare: (opts) => render('message-square', opts, 16),
        merge: (opts) => render('merge', opts, 16),

        // Status & Alerts
        primary: (opts) => render('info', opts, 64),
        info: (opts) => render('info', opts, 64),
        infoCircle: (opts) => render('info-circle', opts, 16),
        warning: (opts) => render('warning', opts, 64),
        danger: (opts) => render('danger', opts, 64),
        success: (opts) => render('success', opts, 16),
        shield: (opts) => render('shield', opts, 16),
        eye: (opts) => render('eye', opts, 16),

        // Folders & Menus
        folder: (opts) => render('folder', opts, 16),
        folderParent: (opts) => render('folder-parent', opts, 16),
        tagMenu: (opts) => render('tag-menu', opts, 14)
    };

    window.Icons = Icons;
})();
