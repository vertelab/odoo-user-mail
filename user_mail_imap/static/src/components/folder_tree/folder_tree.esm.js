/** @odoo-module **/
import { Component, useState } from "@odoo/owl";

export class FolderTree extends Component {
    static template = "user_mail_imap.FolderTree";
    static props = {
        folders: { type: Array, optional: true },
        currentFolder: String,
        onFolderClick: Function,
        onSync: Function,
        openComposer: Function,
    };

    setup() {
        this.state = useState({ collapsed: {} });
    }

    get tree() {
        const t = this._buildTree(this.props.folders || []);
        // Hide the descendants of a collapsed node. `_buildTree` returns a flat
        // list where every node carries its `depth`, so a node is visible only
        // if no ancestor is collapsed. Walking the list in order and tracking
        // the depth below which everything is hidden is enough; the list is
        // already in pre-order (parents before their children).
        let hiddenBelowDepth = Infinity;
        const visible = [];
        for (const f of t) {
            if (f.depth > hiddenBelowDepth) {
                continue;
            }
            visible.push(f);
            hiddenBelowDepth = this.state.collapsed[f.fullName] ? f.depth : Infinity;
        }
        return visible;
    }

    _buildTree(folders) {
        if (!folders.length) return [];

        // Detect delimiter
        let delim = '/';
        for (const f of folders) {
            if (f.delimiter && f.delimiter !== '\\' && f.delimiter !== 'NIL') {
                // Strip any surrounding quotes from delimiter
                delim = f.delimiter.replace(/^"/, '').replace(/"$/, '');
                if (delim) break;
            }
        }
        console.log('FolderTree: using delimiter:', JSON.stringify(delim));

        // Build tree structure
        const root = {};
        const leafNames = new Set(folders.map(f => f.name));

        for (const f of folders) {
            const parts = f.name.split(delim);
            let node = root;
            for (let i = 0; i < parts.length; i++) {
                const part = parts[i];
                if (!node[part]) {
                    node[part] = { children: {} };
                }
                if (i === parts.length - 1) {
                    // This is a real folder (can hold messages)
                    node[part].fullName = f.name;
                    node[part].isReal = true;
                }
                node = node[part].children;
            }
        }

        // Also set fullName for virtual parents (namespace without own folder)
        function setFullNames(node, prefix) {
            for (const [name, entry] of Object.entries(node)) {
                if (!entry.fullName) {
                    entry.fullName = prefix ? prefix + delim + name : name;
                    entry.isReal = false;
                }
                if (Object.keys(entry.children).length) {
                    setFullNames(entry.children, entry.fullName);
                }
            }
        }
        setFullNames(root, '');

        // Flatten
        const result = [];
        const inboxItems = [];

        function walk(node, depth, isInbox) {
            const keys = Object.keys(node).sort();
            const sorted = [
                ...keys.filter(k => k.toUpperCase() === 'INBOX'),
                ...keys.filter(k => k.toUpperCase() !== 'INBOX').sort(),
            ];
            for (const name of sorted) {
                const entry = node[name];
                const hasChildren = Object.keys(entry.children).length > 0;
                const target = (isInbox || name.toUpperCase() === 'INBOX') ? inboxItems : result;
                target.push({ name, ...entry, depth, hasChildren });
                if (hasChildren) {
                    walk(entry.children, depth + 1, isInbox || name.toUpperCase() === 'INBOX');
                }
            }
        }

        walk(root, 0, false);
        return [...inboxItems, ...result];
    }

    toggleCollapse(fullName) {
        this.state.collapsed = { ...this.state.collapsed, [fullName]: !this.state.collapsed[fullName] };
    }
}
