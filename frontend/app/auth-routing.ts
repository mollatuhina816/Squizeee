export type AuthUserLike = {
  profession: 'teacher' | 'student';
  is_super_admin?: boolean;
};

export function getPostAuthPath(user: AuthUserLike): string {
  if (user.is_super_admin) return '/admin';
  if (user.profession === 'student') return '/student';
  return '/';
}
