class TagInputHelper {
    constructor() {
        this.tagValidationCache = new Map();
        this.validationTimeouts = new Map();
        this.abortControllers = new Map();

        window.addEventListener('tagCreated', (e) => {
            if (e.detail && e.detail.name) {
                this.tagValidationCache.set(e.detail.name, true);
            }
        });
    }

    // Get plain text from contenteditable div
    getPlainTextFromDiv(div) {
        return div.textContent || '';
    }

    // Get cursor position in contenteditable element
    getCursorPosition(element) {
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return 0;

        const range = selection.getRangeAt(0);
        const preCaretRange = range.cloneRange();
        preCaretRange.selectNodeContents(element);
        preCaretRange.setEnd(range.endContainer, range.endOffset);

        return preCaretRange.toString().length;
    }

    // Set cursor position in contenteditable element
    setCursorPosition(element, offset) {
        const selection = window.getSelection();
        const range = document.createRange();

        let currentOffset = 0;
        let found = false;

        const traverseNodes = (node) => {
            if (found) return;

            if (node.nodeType === Node.TEXT_NODE) {
                const nodeLength = node.textContent.length;
                if (currentOffset + nodeLength >= offset) {
                    range.setStart(node, offset - currentOffset);
                    range.collapse(true);
                    found = true;
                    return;
                }
                currentOffset += nodeLength;
            } else {
                for (let child of node.childNodes) {
                    traverseNodes(child);
                    if (found) return;
                }
            }
        };

        try {
            traverseNodes(element);
            if (!found && element.lastChild) {
                range.setStartAfter(element.lastChild);
                range.collapse(true);
            } else if (!found && !element.lastChild) {
                range.setStart(element, 0);
                range.collapse(true);
            }
            selection.removeAllRanges();
            selection.addRange(range);
        } catch (e) {
            console.error('Error setting cursor:', e);
        }
    }

    // Check if a tag exists
    async checkTagExists(tagName) {
        if (!tagName || !tagName.trim()) return true;
        const normalized = tagName.toLowerCase().trim();

        try {
            const res = await fetch(`/api/tags/${encodeURIComponent(normalized)}`);
            return res.ok;
        } catch (e) {
            console.error('Error checking tag:', e);
            return false;
        }
    }

    // Check multiple tags at once
    async checkTagsBatch(tagNames) {
        if (!tagNames || tagNames.length === 0) return {};

        try {
            const namesParam = tagNames.map(n => encodeURIComponent(n.toLowerCase().trim())).join(',');
            const res = await fetch(`/api/tags?names=${namesParam}`);
            if (res.ok) {
                const tags = await res.json();
                const result = {};
                tagNames.forEach(n => result[n.toLowerCase().trim()] = null);
                tags.forEach(t => result[t.name.toLowerCase().trim()] = t);
                return result;
            }
            return {};
        } catch (e) {
            console.error('Error checking tags batch:', e);
            return {};
        }
    }

    // Check if tag or alias exists (for admin)
    async checkTagOrAliasExists(tagName) {
        if (!tagName || !tagName.trim()) return false;
        const normalized = tagName.toLowerCase().trim();

        try {
            // Check if it's a tag
            const tagRes = await fetch(`/api/tags/${encodeURIComponent(normalized)}`);
            if (tagRes.ok) {
                return true;
            }

            // Check if it's an alias
            const aliasRes = await fetch(`/api/admin/check-alias?name=${encodeURIComponent(normalized)}`);
            if (aliasRes.ok) {
                const data = await aliasRes.json();
                return data.exists;
            }

            return false;
        } catch (e) {
            console.error('Error checking tag/alias:', e);
            return false;
        }
    }

    // Validate and style tags in a contenteditable input
    async validateAndStyleTags(inputElement, options = {}) {
        const {
            validationCache = this.tagValidationCache,
            checkFunction = (tag) => this.checkTagExists(tag),
            invertLogic = false, // If true, invalid means exists (for admin new tags)
            allowWildcards = false, // If true, tokens containing * are never marked invalid
            highlightTags = null // Set of tag names (lowercase) to highlight as new
        } = options;

        if (!inputElement) return;

        const text = this.getPlainTextFromDiv(inputElement);
        const cursorPos = this.getCursorPosition(inputElement);

        // Split by whitespace
        const parts = text.split(/(\s+)/);
        const tags = [];

        // Check each non-whitespace part
        const uncachedTags = new Set();
        for (let part of parts) {
            if (part.trim()) {
                const normalized = part.trim().toLowerCase();
                if (!validationCache.has(normalized)) {
                    uncachedTags.add(normalized);
                }
            }
        }

        // Batch fetch uncached tags if possible
        if (uncachedTags.size > 0) {
            const results = await this.checkTagsBatch(Array.from(uncachedTags));
            for (let tag of uncachedTags) {
                if (results.hasOwnProperty(tag)) {
                    validationCache.set(tag, !!results[tag]);
                } else {
                    // Fallback to individual check if not in batch results
                    const exists = await checkFunction(tag);
                    validationCache.set(tag, exists);
                }
            }
        }

        for (let part of parts) {
            if (part.trim()) {
                const normalized = part.trim().toLowerCase();
                const isValid = validationCache.get(normalized);
                const isWildcardPattern = allowWildcards && (normalized.includes('*') || normalized.includes('?'));
                const isHighlighted = highlightTags && highlightTags.has(normalized);

                let shouldMarkInvalid;
                if (invertLogic) {
                    // When invertLogic is true (e.g. creating new tags), existing tags are invalid (red).
                    shouldMarkInvalid = isValid;
                } else {
                    // Normal mode: valid if it exists in the DB or if it's a valid wildcard pattern.
                    shouldMarkInvalid = !(isValid || isWildcardPattern);
                }

                tags.push({ text: part, isInvalid: shouldMarkInvalid, isHighlighted: isHighlighted });
            } else {
                tags.push({ text: part, isWhitespace: true });
            }
        }

        // Build styled HTML with escaped content
        let html = '';
        for (let tag of tags) {
            if (tag.isWhitespace) {
                html += escapeHtml(tag.text);
            } else if (tag.isInvalid) {
                html += `<span class="invalid-tag">${escapeHtml(tag.text)}</span>`;
            } else if (tag.isHighlighted) {
                html += `<span class="new-tag">${escapeHtml(tag.text)}</span>`;
            } else {
                html += escapeHtml(tag.text);
            }
        }

        const currentText = this.getPlainTextFromDiv(inputElement);
        if (currentText !== text) {
            return;
        }

        // Update content if changed
        if (inputElement.innerHTML !== html) {
            const isFocused = document.activeElement === inputElement;
            inputElement.innerHTML = html || '';
            if (isFocused) {
                inputElement.focus();
            }
            this.setCursorPosition(inputElement, cursorPos);
        }
    }

    wildcardToRegex(pattern) {
        const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&');
        const regexStr = '^' + escaped.replace(/\*/g, '.*').replace(/\?/g, '.?') + '$';
        return new RegExp(regexStr, 'i');
    }

    // Call POST /api/tag-implications/expand with the tags currently in inputElement.
    // Returns true if any implied tags were inserted (caller may want to re-validate).
    async expandImplications(inputElement) {
        const text = this.getPlainTextFromDiv(inputElement);
        const currentTags = text.split(/\s+/).filter(t => t.length > 0);
        if (currentTags.length === 0) return false;

        let data;
        try {
            const response = await fetch('/api/tag-implications/expand', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tags: currentTags })
            });
            if (!response.ok) return false;
            data = await response.json();
        } catch (e) {
            console.error('Error expanding implications:', e);
            return false;
        }

        const impliedTags = (data.implied_tags || []).filter(name => {
            return !currentTags.some(t => t.toLowerCase() === name.toLowerCase());
        });
        if (impliedTags.length === 0) return false;

        const insertText = impliedTags.join(' ') + ' ';

        inputElement.focus();
        const sel = window.getSelection();
        if (!sel.rangeCount || !inputElement.contains(sel.anchorNode)) {
            const range = document.createRange();
            range.selectNodeContents(inputElement);
            range.collapse(false);
            sel.removeAllRanges();
            sel.addRange(range);
        }

        document.execCommand('insertText', false, insertText);
        return true;
    }

    // Setup tag input event listeners
    setupTagInput(inputElement, inputId, options = {}) {
        const {
            onValidate = null,
            validateDelay = 300,
            validationCache = this.tagValidationCache,
            checkFunction = (tag) => this.checkTagExists(tag),
            invertLogic = false,
            expandImplications = true,
            allowWildcards = false, // If true, tokens containing * are never marked invalid
            getHighlightTags = null // Function that returns a Set of tags to highlight
        } = options;

        if (!inputElement) return;

        // Abort and replace any existing listeners for this inputId to prevent duplicates
        if (this.abortControllers.has(inputId)) {
            this.abortControllers.get(inputId).abort();
        }
        const controller = new AbortController();
        const { signal } = controller;
        this.abortControllers.set(inputId, controller);

        // Strip IDE-injected whitespace (newlines/indents) from empty inputs
        if (inputElement.textContent.trim() === '') {
            inputElement.innerHTML = '';
        }

        // Handle input events
        inputElement.addEventListener('input', () => {
            if (this.validationTimeouts.has(inputId)) {
                clearTimeout(this.validationTimeouts.get(inputId));
            }
            const timeout = setTimeout(async () => {
                const highlightTags = getHighlightTags ? getHighlightTags(inputElement) : null;
                await this.validateAndStyleTags(inputElement, {
                    validationCache,
                    checkFunction,
                    invertLogic,
                    allowWildcards,
                    highlightTags
                });
                if (onValidate) onValidate();
            }, validateDelay);
            this.validationTimeouts.set(inputId, timeout);
        }, { signal });

        // Immediate validation and implications expansion on space
        inputElement.addEventListener('keyup', async (e) => {
            if (e.key === ' ') {
                if (this.validationTimeouts.has(inputId)) {
                    clearTimeout(this.validationTimeouts.get(inputId));
                }

                let highlightTags = getHighlightTags ? getHighlightTags(inputElement) : null;
                await this.validateAndStyleTags(inputElement, {
                    validationCache,
                    checkFunction,
                    invertLogic,
                    allowWildcards,
                    highlightTags
                });
                if (expandImplications) {
                    const added = await this.expandImplications(inputElement);
                    if (added) {
                        highlightTags = getHighlightTags ? getHighlightTags(inputElement) : null;
                        await this.validateAndStyleTags(inputElement, {
                            validationCache,
                            checkFunction,
                            invertLogic,
                            allowWildcards,
                            highlightTags
                        });
                    }
                }
                if (onValidate) onValidate();
            }
        }, { signal });

        // Prevent default Enter behavior
        inputElement.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
            }
        }, { signal });

        // Paste as plain text
        inputElement.addEventListener('paste', (e) => {
            e.preventDefault();
            const text = e.clipboardData.getData('text/plain');
            document.execCommand('insertText', false, text);
        }, { signal });
    }

    // Get valid tags from input (filter out invalid ones)
    getValidTagsFromInput(inputElement, validationCache = this.tagValidationCache) {
        const text = this.getPlainTextFromDiv(inputElement);
        const allTags = text.split(/\s+/).filter(t => t.length > 0);

        const validTags = [];
        for (const tag of allTags) {
            const normalized = tag.toLowerCase().trim();
            const isValid = validationCache.get(normalized);
            if (isValid !== false) {
                validTags.push(tag);
            }
        }

        return validTags;
    }

    // Clear validation cache
    clearCache() {
        this.tagValidationCache.clear();
    }

    // Clear all timeouts
    clearTimeouts() {
        for (const timeout of this.validationTimeouts.values()) {
            clearTimeout(timeout);
        }
        this.validationTimeouts.clear();
        for (const controller of this.abortControllers.values()) {
            controller.abort();
        }
        this.abortControllers.clear();
    }

    // Cleanup
    destroy() {
        this.clearTimeouts();
        this.clearCache();
    }
}
