export interface SymbolReferenceItem {
  syntax: string;
  meaning: string;
  note?: string;
}

export interface SymbolReferenceSection {
  title: string;
  items: SymbolReferenceItem[];
}

export const symbolReferenceSections: SymbolReferenceSection[] = [
  {
    title: '常用符号',
    items: [
      { syntax: '<脑> / <wil>', meaning: '意志', note: '也支持直接输入 🧠' },
      { syntax: '<书> / <int>', meaning: '知识', note: '也支持 📚' },
      { syntax: '<拳> / <com>', meaning: '战斗', note: '也支持 👊' },
      { syntax: '<脚> / <agi>', meaning: '敏捷', note: '也支持 🦶' },
      { syntax: '<?> / <wild>', meaning: '万能技能', note: '建议统一用 <?>' },
      { syntax: '<守护者> / <gua>', meaning: '守护者', note: '也支持 🛡️' },
      { syntax: '<探求者> / <see>', meaning: '探求者', note: '也支持 🔍' },
      { syntax: '<流浪者> / <rog>', meaning: '流浪者', note: '也支持 🚶' },
      { syntax: '<潜修者> / <mys>', meaning: '潜修者', note: '也支持 🧘' },
      { syntax: '<生存者> / <sur>', meaning: '生存者', note: '也支持 🏕️' },
      { syntax: '<调查员> / <per>', meaning: '调查员数量', note: '也支持 🕵️' },
      { syntax: '<启动> / <箭头> / <act>', meaning: '启动能力', note: '也支持 ➡️' },
      { syntax: '<反应> / <rea>', meaning: '反应能力', note: '也支持 ⭕' },
      { syntax: '<免费> / <fre>', meaning: '免费触发', note: '也支持 ⚡' },
      { syntax: '<骷髅> / <sku>', meaning: '骷髅标记', note: '也支持 💀' },
      { syntax: '<异教徒> / <cul>', meaning: '异教徒标记', note: '也支持 👤' },
      { syntax: '<石板> / <tab>', meaning: '石板标记', note: '也支持 📜' },
      { syntax: '<古神> / <mon>', meaning: '古神标记', note: '也支持 👹' },
      { syntax: '<触手> / <大失败> / <ten>', meaning: '自动失败', note: '也支持 🐙' },
      { syntax: '<旧印> / <大成功> / <eld>', meaning: '古老印记', note: '也支持 ⭐' },
      { syntax: '<独特> / <uni>', meaning: '独特', note: '也支持 🏅' },
      { syntax: '<点> / <bul>', meaning: '项目符号', note: '也支持 🔵' },
      { syntax: '<祝福> / <ble>', meaning: '祝福标记', note: '也支持 🌟' },
      { syntax: '<诅咒> / <cur>', meaning: '诅咒标记', note: '也支持 🌑' },
      { syntax: '<雪花> / <frost>', meaning: '霜冻标记', note: '也支持 ❄️' },
      { syntax: '<一>', meaning: '数字 1 图标', note: '少量卡牌会用到' },
      { syntax: '<arrow>', meaning: '箭头字符', note: '输出 →' },
    ],
  },
  {
    title: '正文格式',
    items: [
      { syntax: '【文字】', meaning: '加粗文字', note: '常用于【强制】、【显现】等关键词' },
      { syntax: '{{文字}}', meaning: '转换为【文字】', note: '例如 {{攻击}}' },
      { syntax: '{特性}', meaning: '特性字体', note: '例如 {精英}、{武器}' },
      { syntax: '<t>特性</t>', meaning: '特性字体', note: '等价于 {特性}' },
      { syntax: '[风味文本]', meaning: '转换为风味文本', note: '普通正文中快速写一段风味文字' },
      { syntax: '<flavor>文本</flavor>', meaning: '风味文本', note: '可带 align、quote、padding 等参数' },
      { syntax: '<i>文本</i>', meaning: '斜体', note: '常用于括注和英文文本' },
      { syntax: '<b>文本</b>', meaning: '粗体', note: '需要手动控制粗体时使用' },
      { syntax: '<br>', meaning: '换行', note: '普通换行也会生效' },
      { syntax: '<par>', meaning: '新段落', note: '段落间距比普通换行更大' },
      { syntax: '<hr>', meaning: '横线分隔', note: '常用于剧情/结局段落分隔' },
      { syntax: '<center>文本</center>', meaning: '居中', note: '适合短列表或标题' },
      { syntax: '<right>文本</right>', meaning: '右对齐', note: '常用于“继续阅读背面”' },
      { syntax: '<nbsp> 或 _', meaning: '不断行空格', note: '避免关键短语断开' },
      { syntax: '--- / -- / ...', meaning: '标点转换', note: '分别转为 —、–、…' },
    ],
  },
  {
    title: '快捷关键词',
    items: [
      { syntax: '<pre> / <猎物>', meaning: '猎物', note: '自动使用加粗关键词格式' },
      { syntax: '<spa> / <生成>', meaning: '生成', note: '自动使用加粗关键词格式' },
      { syntax: '<for> / <强制>', meaning: '强制', note: '自动使用加粗关键词格式' },
      { syntax: '<hau> / <闹鬼>', meaning: '闹鬼', note: '自动使用加粗关键词格式' },
      { syntax: '<obj> / <目标>', meaning: '目标', note: '自动使用加粗关键词格式' },
      { syntax: '<pat> / <巡逻>', meaning: '巡逻', note: '输出本地化关键词' },
      { syntax: '<rev> / <显现>', meaning: '显现', note: '自动使用加粗关键词格式' },
      { syntax: '<res>1</res>', meaning: '结局跳转', note: '中文约为【(→结局1)】' },
      { syntax: '<upg> / <升级>', meaning: '升级方框', note: '输出 ☐' },
      { syntax: '<fullname>', meaning: '当前卡名', note: '自动去掉独特标记' },
      { syntax: '<fullnameb>', meaning: '对侧卡名', note: '双面卡引用时使用' },
    ],
  },
];
