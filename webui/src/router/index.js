import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: () => import('@/pages/HomePage.vue'),
      children: [
        {
          path: '',
          name: 'search',
          component: () => import('@/views/SearchView.vue'),
          meta: {
            title: '关键词搜索',
            keepAlive: true,
            viewKey: 'search'
          }
        },
        {
          path: 'mission-book',
          name: 'mission-book',
          component: () => import('@/views/MissionBookView.vue'),
          meta: {
            title: '任务 / 书籍搜索',
            keepAlive: true,
            viewKey: 'mission-book'
          }
        },
        {
          path: 'message',
          name: 'message',
          component: () => import('@/views/MessageView.vue'),
          meta: {
            title: '短信搜索',
            keepAlive: true,
            viewKey: 'message'
          }
        },
        {
          path: 'voice',
          name: 'voice',
          component: () => import('@/views/AvatarAtlasView.vue'),
          props: {
            kind: 'voice',
            title: '角色语音搜索',
            eyebrow: 'Voice Atlas',
            avatarPlaceholder: '输入角色名',
            searchPlaceholder: '输入语音标题或台词片段',
            emptyText: '没有找到匹配的角色语音角色',
            viewActionLabel: '查看语音',
            viewKey: 'voice'
          },
          meta: {
            title: '角色语音搜索',
            keepAlive: true,
            viewKey: 'voice'
          }
        },
        {
          path: 'story',
          name: 'story',
          component: () => import('@/views/AvatarAtlasView.vue'),
          props: {
            kind: 'story',
            title: '角色故事搜索',
            eyebrow: 'Story Atlas',
            avatarPlaceholder: '输入角色名',
            searchPlaceholder: '输入故事标题或正文片段',
            emptyText: '没有找到匹配的角色故事角色',
            viewActionLabel: '查看故事',
            viewKey: 'story'
          },
          meta: {
            title: '角色故事搜索',
            keepAlive: true,
            viewKey: 'story'
          },
        },
        {
          path: 'detail',
          name: 'detail',
          component: () => import('@/views/DetailView.vue'),
          meta: {
            title: '详情',
            keepAlive: false
          }
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/SettingsView.vue'),
          meta: {
            title: '设置',
            keepAlive: true,
            viewKey: 'settings'
          }
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

export default router
