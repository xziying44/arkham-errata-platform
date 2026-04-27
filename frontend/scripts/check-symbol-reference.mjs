import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import assert from 'node:assert/strict';

const currentDir = dirname(fileURLToPath(import.meta.url));
const sourcePath = resolve(currentDir, '../src/components/workbench/symbolReference.ts');
const source = readFileSync(sourcePath, 'utf8');

for (const title of ['常用符号', '正文格式', '快捷关键词']) {
  assert(source.includes(`title: '${title}'`), `缺少帮助分组：${title}`);
}

assert(!source.includes("title: '图片/复杂排版'"), '不应显示图片/复杂排版分组');

for (const token of ['<脑>', '<启动>', '<骷髅>', '【文字】', '{特性}', '<flavor>文本</flavor>', '<pre>', '<res>1</res>']) {
  assert(source.includes(token), `缺少参考写法：${token}`);
}

console.log('符号参考表内容检查通过');
