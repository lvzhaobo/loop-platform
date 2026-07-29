# UI 规范(清爽学习风,确定数值)

## 配色
- 主色(学习蓝):`#1a73e8`
- 强调/成功(报名绿):`#34a853`
- 背景白:`#FFFFFF`;正文文字 `#333333`;次要/元信息 `#888888`

## 列表页
- 顶部标题栏,站点名居左
- 课程列表为卡片网格,每门一张卡片
- 每张卡片根元素带 class `course-card`,且**必须同时包含以下四个子元素**(硬性要求,每张卡片缺一不可):
  - 封面图:`<img class="course-cover">`
  - 标题:`class="course-title"`
  - 元信息(讲师·难度·时长):`class="course-meta"`
  - 简介:`class="course-summary"`
- 卡片 hover 时标题变主色 `#1a73e8`

## 详情页
- 顶部封面图 + 大标题 + 讲师·难度·时长元信息
- 报名按钮带 class `btn-enroll`,使用强调绿 `#34a853`
- 课程大纲/正文容器根元素带 class `course-outline`,展示 content 正文
- 底部返回列表链接

## 字号
- 列表标题 18px、详情标题 28px、正文 16px、元信息 13px

## 结构标记(compile_spec 从此表派生 case.json 的 UI 字段)
| 键                 | 值                                                     |
|--------------------|--------------------------------------------------------|
| list_marker        | course-card                                            |
| list_card_children | course-cover, course-title, course-meta, course-summary |
| detail_markers     | btn-enroll, course-outline                             |
| required_colors    | #1a73e8, #34a853                                       |
