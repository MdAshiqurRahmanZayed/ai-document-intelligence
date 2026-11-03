import { DocumentDetail } from "@/components/DocumentDetail";

export const metadata = { title: "Document · Document Intelligence" };

export default async function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  const { id } = await params;
  return <DocumentDetail id={id} />;
}
