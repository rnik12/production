import Twin from "./components/twin";

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 to-gray-100">
      <div className="container mx-auto px-4 py-10">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-4xl font-bold text-center text-gray-800 mb-2">
            AI Digital Twin
          </h1>
          <p className="text-center text-gray-600 mb-8">
            Deployed on AWS App Runner
          </p>

          <div className="h-[640px]">
            <Twin />
          </div>

          <footer className="mt-8 text-center text-sm text-gray-500">
            <p>Week 2 Deployment (App Runner)</p>
          </footer>
        </div>
      </div>
    </main>
  );
}
