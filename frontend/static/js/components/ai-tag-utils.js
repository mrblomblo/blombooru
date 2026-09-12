class AITagUtils {
    static extractAIData(metadata) {
        if (!metadata || typeof metadata !== 'object') return null;
        if (metadata.ai && typeof metadata.ai === 'object' && Object.keys(metadata.ai).length > 0) {
            return metadata.ai;
        }
        return null;
    }

    static extractAIPrompt(metadata) {
        if (!metadata) return null;
        if (typeof metadata === 'string') {
            return metadata.trim() || null;
        }
        if (metadata.ai && typeof metadata.ai.prompt === 'string' && metadata.ai.prompt.trim()) {
            return metadata.ai.prompt.trim();
        }
        if (typeof metadata.prompt === 'string' && metadata.prompt.trim()) {
            return metadata.prompt.trim();
        }
        return null;
    }

    static extractPromptTags(metadata) {
        if (!metadata) return [];

        if (typeof metadata === 'string') {
            return this.parsePromptTags(metadata);
        }

        if (Array.isArray(metadata.ai?.prompt_tags)) {
            return metadata.ai.prompt_tags;
        }

        if (Array.isArray(metadata.prompt_tags)) {
            return metadata.prompt_tags;
        }

        const prompt = this.extractAIPrompt(metadata);
        return prompt ? this.parsePromptTags(prompt) : [];
    }

    static parsePromptTags(prompt) {
        if (!prompt || typeof prompt !== 'string') return [];

        const cleaned = prompt.replace(/<[^>]+>/g, ' ').replace(/\bembedding:[^\s,]+\b/gi, ' ');
        const segments = cleaned.split(/[\r\n,]+/);
        const tags = [];
        const seen = new Set();

        for (let seg of segments) {
            seg = seg.trim();
            if (!seg) continue;

            if (seg.toUpperCase() === 'BREAK' || seg.toUpperCase() === 'AND') {
                continue;
            }

            // Strip enclosing weight brackets/parentheses: (tag:1.2), ((tag)), [tag]
            seg = seg.replace(/^[(\[{]+/, '').replace(/[:0-9.]*[\)\]}]+$/, '').trim();
            if (!seg) continue;

            // Clean punctuation and quotes
            seg = seg.replace(/^[ ,;"']+|[ ,;"']+$/g, '').trim();
            while (seg.endsWith('.') && !seg.endsWith('..')) {
                seg = seg.slice(0, -1).trim();
            }

            // Strip leading conjunctions/articles: "and black gloves" -> "black gloves"
            seg = seg.replace(/^(and|with|a|an|the)\s+/i, '').trim();
            if (!seg) continue;

            const normalized = seg.replace(/\s+/g, '_').toLowerCase();
            if (normalized.length > 55 || normalized.split('_').length > 7) {
                continue;
            }

            if (!seen.has(normalized)) {
                seen.add(normalized);
                tags.push(normalized);
            }
        }

        return tags;
    }
}

if (typeof window !== 'undefined') {
    window.AITagUtils = AITagUtils;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = AITagUtils;
}
